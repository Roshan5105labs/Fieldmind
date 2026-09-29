from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODELS_DIR = "./models"

model = TextEmbedding(model_name=MODEL_NAME, cache_dir=MODELS_DIR)
vector = list(model.embed(["test sentence"]))[0]
print(f"Downloaded {MODEL_NAME}, vector size = {len(vector)}")