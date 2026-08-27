import importlib

for m in ["torchvision", "transformers", "sentence_transformers"]:
    try:
        mod = importlib.import_module(m)
        print(f"{m}: OK {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"{m}: FAIL -> {type(e).__name__}: {e}")

# Try a real encode with the two models the retriever uses
try:
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer("ncbi/MedCPT-Embedding")
    v = m.encode(["blood pressure 130/82"])
    print("MedCPT encode OK shape", getattr(v, "shape", None) or len(v))
except Exception as e:
    print("MedCPT encode FAIL ->", type(e).__name__, e)

try:
    from sentence_transformers import SentenceTransformer

    m2 = SentenceTransformer("BAAI/bge-m3")
    v2 = m2.encode(["hypertension on amlodipine"])
    print("BGE-M3 encode OK shape", getattr(v2, "shape", None) or len(v2))
except Exception as e:
    print("BGE-M3 encode FAIL ->", type(e).__name__, e)
