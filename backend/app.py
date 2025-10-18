import os, io, base64, json, re
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SYSTEM = """
Eres un analista farmacéutico. Observas UNA foto de un blíster o pastilla.
Devuelve SOLO JSON válido con este esquema:
{
  "name":"<marca o genérico si se ve, o mejor suposición>",
  "strength":"<ej: 500 mg, 10 mg, vacío si no se ve>",
  "active_ingredient":"<si se infiere, si no vacío>",
  "what_for":"<2-4 líneas de uso general en lenguaje claro. Nunca dosis personalizadas.>",
  "use_cases":["<3-5 casos de uso comunes y no personalizados, p. ej., 'dolor de cabeza leve'>"],
  "common_warnings":["<2-5 advertencias genéricas del principio activo o su clase>"]
}
Reglas:
- No texto fuera del JSON.
- Si el nombre/marca es claro, infiere clase terapéutica y rellena SIEMPRE what_for, use_cases y common_warnings.
- Si hay ambigüedad, suposición razonable y deja en blanco lo imposible.
"""

app = FastAPI(title="FotoMedi – Vision API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EMPTY = {
    "name": "",
    "strength": "",
    "active_ingredient": "",
    "what_for": "",
    "use_cases": [],
    "common_warnings": []
}

def extract_json(txt: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", txt or "")
    if not m:
        return EMPTY.copy()
    try:
        data = json.loads(m.group(0))
        # normaliza claves faltantes
        out = EMPTY.copy()
        out.update({k: v for k, v in data.items() if k in out})
        # coerciones simples
        if not isinstance(out["use_cases"], list): out["use_cases"] = []
        if not isinstance(out["common_warnings"], list): out["common_warnings"] = []
        return out
    except Exception:
        return EMPTY.copy()

def to_data_url(raw: bytes, content_type: str | None) -> str:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        s = max(w, h)
        if s > 1600:
            scale = 1600 / s
            img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        mime = content_type or "image/jpeg"
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:{mime};base64,{b64}"

def enrich_fields(client, info: dict) -> dict:
    need_use = not info.get("what_for")
    need_warn = not info.get("common_warnings")
    need_cases = not info.get("use_cases")
    if not (need_use or need_warn or need_cases):
        return info
    name = info.get("name") or info.get("active_ingredient") or "desconocido"
    prompt = f"""
Devuelve SOLO JSON con los campos faltantes sobre "{name}":
{{
  "what_for":"<2-4 líneas de uso general>",
  "use_cases":["<3-5 casos comunes no personalizados>"],
  "common_warnings":["<2-5 advertencias genéricas>"]
}}
No des dosis ni consejos personalizados.
"""
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return info
        r = OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": prompt.strip()}],
        )
        add = extract_json(r.choices[0].message.content)
        if need_use and add.get("what_for"): info["what_for"] = add["what_for"]
        if need_cases and isinstance(add.get("use_cases"), list): info["use_cases"] = add["use_cases"]
        if need_warn and isinstance(add.get("common_warnings"), list):
            info["common_warnings"] = add["common_warnings"]
    except Exception:
        pass
    return info

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze")
async def analyze(image: UploadFile = File(...)):
    try:
        from openai import OpenAI
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SDK openai no disponible: {e}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Falta OPENAI_API_KEY en el backend.")

    client = OpenAI(api_key=api_key)
    raw = await image.read()
    data_url = to_data_url(raw, image.content_type)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM.strip()},
                {"role": "user", "content": [
                    {"type": "text", "text": "Analiza la imagen y devuelve SOLO el JSON pedido."},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
        )
        info = extract_json(resp.choices[0].message.content)
        info = enrich_fields(client, info)
        return {"info": info}
    except Exception as e:
        msg = repr(e)
        if "insufficient_quota" in msg or "code': 429" in msg:
            raise HTTPException(status_code=429, detail="Límite de uso alcanzado en OpenAI (insufficient_quota).")
        raise HTTPException(status_code=500, detail=f"Vision API error: {e}")
