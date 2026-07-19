"""Image Registration Service — ORB feature matching, homography, overlay generation.

Module 4: Clinical Image Comparison for wound/skin monitoring.

Pipeline:
  1. Load two images (previous visit, current visit)
  2. ORB feature detection + extraction on both
  3. BFMatcher + Lowe's ratio test for good matches
  4. RANSAC homography computation for geometric alignment
  5. Warp + overlay generation (semi-transparent composite)
  6. Compute metrics: area change %, edge convergence, color histogram shift

Usage:
    from app.services.image_registration import ImageRegistrationService
    reg = ImageRegistrationService()
    result = await reg.compare(img_prev_path, img_curr_path)
    # -> {"matches": n, "homography": [...], "overlay_path": "...", "metrics": {...}}
"""

from __future__ import annotations

import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# ─── Registration Result ────────────────────────────

@dataclass
class ComparisonMetrics:
    area_change_pct: float = 0.0
    edge_convergence_score: float = 0.0
    color_histogram_shift: float = 0.0
    num_matches: int = 0
    num_good_matches: int = 0
    match_ratio: float = 0.0
    homography_confidence: float = 0.0

@dataclass
class RegistrationResult:
    status: str
    matched: bool
    metrics: ComparisonMetrics
    overlay_path: Optional[str] = None
    warped_previous_path: Optional[str] = None
    keypoints_prev: int = 0
    keypoints_curr: int = 0
    message: str = ""


# ─── Image Registration Service ─────────────────────

class ImageRegistrationService:
    """ORB-based image registration for clinical wound/skin comparison.

    Uses OpenCV for:
      - ORB feature detection (free, fast, CPU-based)
      - BFMatcher with Hamming distance
      - Lowe's ratio test for match filtering
      - RANSAC homography for geometric alignment
      - Semi-transparent overlay generation
      - Area/edge/color metrics computation
    """

    def __init__(
        self,
        nfeatures: int = 1000,
        scale_factor: float = 1.2,
        nlevels: int = 8,
        lowe_ratio: float = 0.75,
        ransac_reproj_threshold: float = 4.0,
        min_good_matches: int = 10,
    ):
        self.nfeatures = nfeatures
        self.scale_factor = scale_factor
        self.nlevels = nlevels
        self.lowe_ratio = lowe_ratio
        self.ransac_reproj_threshold = ransac_reproj_threshold
        self.min_good_matches = min_good_matches

        self._orb = None
        self._output_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "uploads", "comparisons",
        )

    def _ensure_output_dir(self):
        os.makedirs(self._output_dir, exist_ok=True)

    def _get_orb(self):
        """Lazy-load OpenCV ORB detector."""
        if self._orb is None:
            import cv2
            self._orb = cv2.ORB_create(
                nfeatures=self.nfeatures,
                scaleFactor=self.scale_factor,
                nlevels=self.nlevels,
            )
        return self._orb

    async def compare(
        self,
        image_prev_path: str,
        image_curr_path: str,
        patient_id: Optional[str] = None,
    ) -> RegistrationResult:
        """Compare two images using ORB feature matching.

        Args:
            image_prev_path: Path to the previous visit's image.
            image_curr_path: Path to the current visit's image.
            patient_id: Optional patient UUID for organizing output files.

        Returns:
            RegistrationResult with match status, overlay path, and metrics.
        """
        import cv2

        self._ensure_output_dir()

        # Validate inputs
        if not os.path.exists(image_prev_path):
            return RegistrationResult(
                status="error", matched=False,
                metrics=ComparisonMetrics(),
                message=f"Previous image not found: {image_prev_path}",
            )
        if not os.path.exists(image_curr_path):
            return RegistrationResult(
                status="error", matched=False,
                metrics=ComparisonMetrics(),
                message=f"Current image not found: {image_curr_path}",
            )

        # Load images
        img_prev = cv2.imread(image_prev_path, cv2.IMREAD_COLOR)
        img_curr = cv2.imread(image_curr_path, cv2.IMREAD_COLOR)

        if img_prev is None or img_curr is None:
            return RegistrationResult(
                status="error", matched=False,
                metrics=ComparisonMetrics(),
                message="Failed to load one or both images",
            )

        # Convert to grayscale for feature detection
        gray_prev = cv2.cvtColor(img_prev, cv2.COLOR_BGR2GRAY)
        gray_curr = cv2.cvtColor(img_curr, cv2.COLOR_BGR2GRAY)

        # Step 1: ORB feature detection
        orb = self._get_orb()
        kp_prev, des_prev = orb.detectAndCompute(gray_prev, None)
        kp_curr, des_curr = orb.detectAndCompute(gray_curr, None)

        if des_prev is None or des_curr is None:
            return RegistrationResult(
                status="error", matched=False,
                metrics=ComparisonMetrics(),
                message="No features detected in one or both images",
                keypoints_prev=len(kp_prev) if kp_prev is not None else 0,
                keypoints_curr=len(kp_curr) if kp_curr is not None else 0,
            )

        # Step 2: BFMatcher with Hamming distance (ORB uses binary descriptors)
        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        matches = bf.knnMatch(des_prev, des_curr, k=2)

        # Step 3: Lowe's ratio test
        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < self.lowe_ratio * n.distance:
                    good_matches.append(m)

        num_matches = len(good_matches)
        match_ratio = num_matches / max(len(matches), 1)

        logger.info(
            "ORB: prev=%d keypoints, curr=%d keypoints, matches=%d, good=%d (ratio=%.2f)",
            len(kp_prev), len(kp_curr), len(matches), num_matches, match_ratio,
        )

        # Step 4: Check if we have enough matches for homography
        if num_matches < self.min_good_matches:
            # Generate simple side-by-side overlay anyway
            overlay_path = self._create_side_by_side(img_prev, img_curr)
            metrics = ComparisonMetrics(
                num_matches=num_matches,
                num_good_matches=num_matches,
                match_ratio=round(match_ratio, 4),
                edge_convergence_score=self._compute_edge_convergence(gray_prev, gray_curr),
                color_histogram_shift=self._compute_color_shift(img_prev, img_curr),
            )
            return RegistrationResult(
                status="ok", matched=False,
                metrics=metrics,
                overlay_path=overlay_path,
                keypoints_prev=len(kp_prev),
                keypoints_curr=len(kp_curr),
                message=f"Only {num_matches} good matches (need {self.min_good_matches}). Using side-by-side.",
            )

        # Step 5: Extract matched keypoints for homography
        src_pts = np.float32([kp_prev[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_curr[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        # Step 6: RANSAC homography
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, self.ransac_reproj_threshold)

        inlier_count = np.sum(mask) if mask is not None else 0
        homography_confidence = inlier_count / max(num_matches, 1)

        if H is None:
            logger.warning("Homography computation failed — using side-by-side fallback")
            overlay_path = self._create_side_by_side(img_prev, img_curr)
            metrics = ComparisonMetrics(
                num_matches=num_matches,
                num_good_matches=num_matches,
                match_ratio=round(match_ratio, 4),
                edge_convergence_score=self._compute_edge_convergence(gray_prev, gray_curr),
                color_histogram_shift=self._compute_color_shift(img_prev, img_curr),
            )
            return RegistrationResult(
                status="ok", matched=False,
                metrics=metrics,
                overlay_path=overlay_path,
                keypoints_prev=len(kp_prev),
                keypoints_curr=len(kp_curr),
                message="Homography failed. Using side-by-side.",
            )

        # Step 7: Warp previous image to align with current
        h_prev, w_prev = img_prev.shape[:2]
        h_curr, w_curr = img_curr.shape[:2]
        warped_prev = cv2.warpPerspective(img_prev, H, (w_curr, h_curr))

        # Step 8: Generate overlay (semi-transparent blend)
        comparison_id = uuid.uuid4()
        overlay_filename = f"overlay_{comparison_id}.jpg"
        overlay_path = os.path.join(self._output_dir, overlay_filename)

        overlay = cv2.addWeighted(warped_prev, 0.5, img_curr, 0.5, 0)
        cv2.imwrite(overlay_path, overlay)

        # Also save the warped version for the UI
        warped_filename = f"warped_{comparison_id}.jpg"
        warped_path = os.path.join(self._output_dir, warped_filename)
        cv2.imwrite(warped_path, warped_prev)

        # Step 9: Compute metrics
        area_change = self._compute_area_change(warped_prev, img_curr)
        edge_score = self._compute_edge_convergence(gray_prev, gray_curr)
        color_shift = self._compute_color_shift(img_prev, img_curr)

        metrics = ComparisonMetrics(
            area_change_pct=round(area_change, 2),
            edge_convergence_score=round(edge_score, 4),
            color_histogram_shift=round(color_shift, 4),
            num_matches=num_matches,
            num_good_matches=num_matches,
            match_ratio=round(match_ratio, 4),
            homography_confidence=round(homography_confidence, 4),
        )

        logger.info(
            "Registration complete: area_change=%.1f%% edge=%.4f color_shift=%.4f overlay=%s",
            area_change, edge_score, color_shift, overlay_path,
        )

        return RegistrationResult(
            status="ok",
            matched=True,
            metrics=metrics,
            overlay_path=overlay_path,
            warped_previous_path=warped_path,
            keypoints_prev=len(kp_prev),
            keypoints_curr=len(kp_curr),
            message=f"Matched with {num_matches} good features (confidence={homography_confidence:.2f})",
        )

    # ─── Metrics Computation ─────────────────────────

    def _compute_area_change(
        self, warped_prev: np.ndarray, img_curr: np.ndarray,
    ) -> float:
        """Estimate percentage area change between aligned images.

        Uses grayscale threshold difference as a proxy for tissue/area change.
        """
        import cv2
        gray_prev = cv2.cvtColor(warped_prev, cv2.COLOR_BGR2GRAY)
        gray_curr = cv2.cvtColor(img_curr, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        gray_prev = cv2.GaussianBlur(gray_prev, (5, 5), 0)
        gray_curr = cv2.GaussianBlur(gray_curr, (5, 5), 0)

        # Compute absolute difference
        diff = cv2.absdiff(gray_prev, gray_curr)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # Percentage of pixels that changed
        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = cv2.countNonZero(thresh)

        return (changed_pixels / max(total_pixels, 1)) * 100.0

    def _compute_edge_convergence(
        self, gray_prev: np.ndarray, gray_curr: np.ndarray,
    ) -> float:
        """Compute Canny edge convergence score between two images.

        Higher score = better edge alignment.
        """
        import cv2
        edges_prev = cv2.Canny(gray_prev, 50, 150)
        edges_curr = cv2.Canny(gray_curr, 50, 150)

        # Compute Jaccard similarity of edge pixels
        intersection = cv2.bitwise_and(edges_prev, edges_curr)
        union = cv2.bitwise_or(edges_prev, edges_curr)

        inter_sum = np.sum(intersection > 0)
        union_sum = np.sum(union > 0)

        if union_sum == 0:
            return 1.0  # Both images have no edges (both blank)

        return inter_sum / union_sum

    def _compute_color_shift(
        self, img_prev: np.ndarray, img_curr: np.ndarray,
    ) -> float:
        """Compute color histogram shift as a measure of visual change.

        Returns Bhattacharyya distance between color histograms.
        """
        import cv2

        def hist(image):
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            h_bins = 50
            s_bins = 60
            hist_size = [h_bins, s_bins]
            h_ranges = [0, 180]
            s_ranges = [0, 256]
            ranges = h_ranges + s_ranges
            hist = cv2.calcHist([hsv], [0, 1], None, hist_size, ranges)
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            return hist

        h_prev = hist(img_prev)
        h_curr = hist(img_curr)
        distance = cv2.compareHist(h_prev, h_curr, cv2.HISTCMP_BHATTACHARYYA)
        return float(distance)

    def _create_side_by_side(
        self, img_prev: np.ndarray, img_curr: np.ndarray,
    ) -> str:
        """Create a side-by-side comparison when registration fails."""
        import cv2
        comparison_id = uuid.uuid4()
        filename = f"sidebyside_{comparison_id}.jpg"
        filepath = os.path.join(self._output_dir, filename)

        h = max(img_prev.shape[0], img_curr.shape[0])
        w_prev = img_prev.shape[1]
        w_curr = img_curr.shape[1]

        # Resize to same height
        prev_resized = cv2.resize(img_prev, (int(w_prev * h / img_prev.shape[0]), h))
        curr_resized = cv2.resize(img_curr, (int(w_curr * h / img_curr.shape[0]), h))

        side_by_side = np.hstack([prev_resized, curr_resized])
        cv2.imwrite(filepath, side_by_side)
        return filepath


# ─── Global instance ────────────────────────────────

image_registration_service = ImageRegistrationService()
