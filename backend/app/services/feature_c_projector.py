"""Feature C — Cross-Modal Linear Projector Training.

Trains W: ℝ^512 → ℝ^1024 using InfoNCE loss on CheXpert image–report pairs
(caption–image alignment) plus curated wound photo–summary pairs from
the image registration feature.

The projector maps BiomedCLIP image embeddings (512d) into BGE-M3 text space
(1024d) so that cross-modal search works without a second collection.

Usage:
    from app.services.feature_c_projector import ProjectorTrainer
    trainer = ProjectorTrainer()
    W = await trainer.train(image_embs, text_embs)
    metrics = await trainer.evaluate(W, held_out)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ─── InfoNCE Loss (NumPy implementation) ───────────────────


def infonce_loss(
    projected_images: np.ndarray,  # (N, 1024)
    text_embeddings: np.ndarray,  # (N, 1024)
    temperature: float = 0.07,
) -> float:
    """InfoNCE loss: -log(exp(sim(i,t)/τ) / Σ_j exp(sim(i,t_j)/τ)).

    Args:
        projected_images: Image embeddings projected to text space (N, d)
        text_embeddings: Text embeddings (N, d)
        temperature: Softmax temperature (default 0.07)

    Returns:
        Scalar loss value.
    """
    # Normalize embeddings
    proj_norm = projected_images / (np.linalg.norm(projected_images, axis=1, keepdims=True) + 1e-10)
    text_norm = text_embeddings / (np.linalg.norm(text_embeddings, axis=1, keepdims=True) + 1e-10)

    # Similarity matrix (N x N)
    sim = proj_norm @ text_norm.T / temperature

    # Labels: diagonal (i == j) are positive pairs
    n = proj_norm.shape[0]
    labels = np.arange(n)

    # Cross-entropy loss (image→text and text→image)
    loss_i2t = _cross_entropy(sim, labels)
    loss_t2i = _cross_entropy(sim.T, labels)

    return float((loss_i2t + loss_t2i) / 2)


def _cross_entropy(logits: np.ndarray, labels: np.ndarray) -> float:
    """Softmax cross-entropy loss."""
    # Numerically stable softmax
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    softmax = exp / (np.sum(exp, axis=1, keepdims=True) + 1e-10)

    n = len(labels)
    loss = -np.sum(np.log(softmax[np.arange(n), labels] + 1e-10)) / n
    return loss


# ─── Linear Projector Training ─────────────────────────────


@dataclass
class ProjectorConfig:
    """Training configuration for the linear projector."""

    input_dim: int = 512  # BiomedCLIP dimension
    output_dim: int = 1024  # BGE-M3 dimension
    learning_rate: float = 0.01
    num_epochs: int = 50
    batch_size: int = 32
    temperature: float = 0.07
    weight_decay: float = 1e-4


class ProjectorTrainer:
    """Trains linear projector W: ℝ^512 → ℝ^1024 with InfoNCE."""

    def __init__(self, config: Optional[ProjectorConfig] = None):
        self.config = config or ProjectorConfig()

    def train(
        self,
        image_embeddings: np.ndarray,  # (N, 512)
        text_embeddings: np.ndarray,  # (N, 1024)
    ) -> Dict[str, Any]:
        """Train the linear projector using InfoNCE.

        Uses simple SGD (no autograd needed — we implement gradient manually).

        Args:
            image_embeddings: BiomedCLIP image embeddings, shape (N, 512)
            text_embeddings: BGE-M3 text embeddings, shape (N, 1024)

        Returns:
            dict with "W" (trained weight matrix), "loss_history", "final_loss"
        """
        N = image_embeddings.shape[0]
        assert image_embeddings.shape[0] == text_embeddings.shape[0], "Mismatched pair count"

        # Initialize W as identity (padded/truncated)
        W = (
            np.eye(
                self.config.output_dim,
                self.config.input_dim,
            )
            * 0.1
        )  # small init

        img_mean = np.mean(image_embeddings, axis=0)
        txt_mean = np.mean(text_embeddings, axis=0)
        img_std = np.std(image_embeddings, axis=0) + 1e-10
        txt_std = np.std(text_embeddings, axis=0) + 1e-10

        # Normalize inputs
        img_norm = (image_embeddings - img_mean) / img_std
        txt_norm = (text_embeddings - txt_mean) / txt_std

        loss_history = []
        lr = self.config.learning_rate
        wd = self.config.weight_decay
        temp = self.config.temperature

        start = time.time()

        for epoch in range(self.config.num_epochs):
            epoch_losses = []
            # Shuffle
            perm = np.random.permutation(N)

            for i in range(0, N, self.config.batch_size):
                batch_idx = perm[i : i + self.config.batch_size]
                X = img_norm[batch_idx]  # (B, 512)
                Y = txt_norm[batch_idx]  # (B, 1024)

                B = X.shape[0]

                # Forward: project images to text space
                projected = X @ W.T  # (B, 1024)

                # Normalize projected and text
                proj_normed = projected / (np.linalg.norm(projected, axis=1, keepdims=True) + 1e-10)
                txt_normed = Y / (np.linalg.norm(Y, axis=1, keepdims=True) + 1e-10)

                # Similarity
                sim = proj_normed @ txt_normed.T / temp  # (B, B)
                labels = np.arange(B)

                # Loss
                loss = _cross_entropy(sim, labels) + _cross_entropy(sim.T, labels)
                loss /= 2
                epoch_losses.append(loss)

                # Gradient (manual for linear layer with InfoNCE)
                # dL/d(projected) = (1/τ) * (softmax(sim) - one_hot(labels)) @ txt_normed
                shifted = sim - np.max(sim, axis=1, keepdims=True)
                soft = np.exp(shifted) / (np.sum(np.exp(shifted), axis=1, keepdims=True) + 1e-10)
                one_hot = np.eye(B)[labels]
                dL_dsim = (soft - one_hot) / B
                dL_dproj = dL_dsim @ txt_normed / temp

                # d(projected)/dW = X^T
                # dL/dW = dL_dproj^T @ X / B + weight_decay * W
                dW = (dL_dproj.T @ X) / B + wd * W

                # Update
                W -= lr * dW

            avg_loss = float(np.mean(epoch_losses))
            loss_history.append(avg_loss)

            if (epoch + 1) % 10 == 0 or epoch == 0:
                logger.info("Feature C epoch %d/%d: loss=%.4f", epoch + 1, self.config.num_epochs, avg_loss)

        took_sec = time.time() - start
        logger.info(
            "Training complete: %d epochs in %.1fs, final loss=%.4f", self.config.num_epochs, took_sec, loss_history[-1]
        )

        return {
            "W": W,
            "loss_history": loss_history,
            "final_loss": loss_history[-1] if loss_history else float("inf"),
            "training_samples": N,
            "epochs_completed": self.config.num_epochs,
            "took_seconds": round(took_sec, 1),
        }

    def project(self, image_embeddings: np.ndarray, W: np.ndarray) -> np.ndarray:
        """Project image embeddings to text space.

        Args:
            image_embeddings: (N, 512) BiomedCLIP embeddings
            W: (1024, 512) trained weight matrix

        Returns:
            (N, 1024) projected embeddings in BGE-M3 space
        """
        return image_embeddings @ W.T

    @staticmethod
    def recall_at_k(
        projected_queries: np.ndarray,
        gallery: np.ndarray,
        k: int = 5,
    ) -> float:
        """Compute Recall@K for cross-modal retrieval.

        Args:
            projected_queries: (N, 1024) projected image embeddings
            gallery: (N, 1024) text embeddings (same ordering as queries)

        Returns:
            Recall@K fraction.
        """
        N = projected_queries.shape[0]
        query_norm = projected_queries / (np.linalg.norm(projected_queries, axis=1, keepdims=True) + 1e-10)
        gallery_norm = gallery / (np.linalg.norm(gallery, axis=1, keepdims=True) + 1e-10)

        sim = query_norm @ gallery_norm.T  # (N, N)

        hits = 0
        for i in range(N):
            # Top-k indices (excluding self)
            top_k = np.argsort(-sim[i])[: k + 1]
            if i in top_k[:k]:
                hits += 1

        return hits / N if N > 0 else 0.0


# ─── Synthetic Data Generation for Training/Eval ──────────


def generate_synthetic_pairs(
    num_pairs: int = 1000,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate synthetic image-text pairs for testing the projector.

    Creates random 512d image embeddings and 1024d text embeddings with
    a known linear relationship (image = W^T @ text + noise) so we can
    verify the training converges.

    Args:
        num_pairs: Number of synthetic pairs.
        seed: Random seed.

    Returns:
        (image_embeddings (N, 512), text_embeddings (N, 1024))
    """
    rng = np.random.RandomState(seed)

    # True projection matrix (ground truth)
    W_true = rng.randn(1024, 512).astype(np.float32) * 0.1

    # Generate text embeddings
    text_embs = rng.randn(num_pairs, 1024).astype(np.float32)

    # Generate matching image embeddings: image ≈ text @ W_true + noise
    noise = rng.randn(num_pairs, 512).astype(np.float32) * 0.05
    image_embs = text_embs @ W_true + noise

    return image_embs, text_embs


def generate_chexpert_pairs(
    image_dir: Optional[str] = None,
    report_file: Optional[str] = None,
    max_pairs: int = 500,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate CheXpert image–report pairs.

    This function prepares the dataset structure. In production, this reads
    the actual CheXpert dataset and computes embeddings via BiomedCLIP and BGE-M3.

    The stub returns synthetic data with realistic dimensions.

    Args:
        image_dir: Path to CheXpert images (optional).
        report_file: Path to CheXpert reports (optional).
        max_pairs: Maximum number of pairs to include.

    Returns:
        (image_embeddings, text_embeddings) numpy arrays.
    """
    # In production, this would:
    # 1. Load CheXpert images from image_dir
    # 2. Run BiomedCLIP encode on each image
    # 3. Load corresponding reports
    # 4. Run BGE-M3 encode on reports
    # For now, return synthetic
    return generate_synthetic_pairs(num_pairs=max_pairs, seed=123)


# ─── Persistence Helpers ──────────────────────────────────

PROJECTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "projector_weights.npy")


def save_projector(W: np.ndarray) -> str:
    """Save trained projector matrix to disk."""
    os.makedirs(os.path.dirname(PROJECTOR_PATH), exist_ok=True)
    np.save(PROJECTOR_PATH, W)
    logger.info("Saved projector matrix to %s (shape=%s)", PROJECTOR_PATH, W.shape)
    return PROJECTOR_PATH


def load_projector() -> Optional[np.ndarray]:
    """Load projector matrix from disk if available."""
    if os.path.exists(PROJECTOR_PATH):
        W = np.load(PROJECTOR_PATH)
        logger.info("Loaded projector matrix from %s (shape=%s)", PROJECTOR_PATH, W.shape)
        return W
    return None


def generate_wound_pairs(
    comparison_data: Optional[List[Dict]] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate wound photo–summary pairs from image registration data.

    Each comparison from the image registration feature creates a paired
    (image embedding, doctor's summary text embedding) sample.

    Args:
        comparison_data: List of comparison records with image_embedding and summary.

    Returns:
        (image_embeddings, text_embeddings) numpy arrays.
    """
    # In production, this reads from the image_comparisons table
    # and uses stored BiomedCLIP embeddings + Maverick clinical summaries

    # For now, return synthetic data
    return generate_synthetic_pairs(num_pairs=100, seed=7)
