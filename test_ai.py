from dotenv import load_dotenv
load_dotenv()

import time
from app.config import DevelopmentConfig as c
from app.services.ai.llm_harness import OllamaHarness

harness = OllamaHarness(
    base_url=c.OLLAMA_URL,
    model=c.OLLAMA_MODEL,
    connect_timeout=c.OLLAMA_CONNECT_TIMEOUT,
    read_timeout=c.OLLAMA_READ_TIMEOUT,
)

print("URL:", c.OLLAMA_URL)
print("Model:", c.OLLAMA_MODEL)
print("Read timeout:", c.OLLAMA_READ_TIMEOUT)

vitals = {"respiratory_rate": 28, "heart_rate": 130, "systolic_bp": 85,
          "temperature": 36.8, "avpu": "V", "spo2": 91}

start = time.time()
try:
    result = harness.assess(
    vitals=vitals,
    symptoms="chest pain and difficulty breathing",
    situation="chest_pain",
    mews_score=5,
    baseline_severity="HIGH",
)
    print("SUCCESS:", result)
except Exception as e:
    print("FAILED status:", getattr(e, "status", None))
    print("FAILED message:", e)
print("Seconds:", round(time.time() - start, 1))