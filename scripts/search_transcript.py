import json

transcript_path = r"C:\Users\devan\.gemini\antigravity\brain\96d5bb51-16e2-4c56-8ae0-69d3efbc4aa7\.system_generated\logs\transcript.jsonl"
with open(transcript_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "Confusion Matrix Restatement" in line or "125" in line:
            obj = json.loads(line)
            if obj.get("type") == "PLANNER_RESPONSE":
                content = obj.get("content", "")
                if "Confusion" in content:
                    print(f"Step {i}:")
                    print(content[:1500])
                    print("="*40)
