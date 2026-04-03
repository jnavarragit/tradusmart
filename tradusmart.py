import os
import re
import time
from datetime import datetime
from openai import OpenAI

# =========================================================
# CONFIG
# =========================================================

INPUT_DIR = r"C:\Users\javier\Desktop\xJavier\videos NDS\paratraducir"
OUTPUT_DIR = r"C:\Users\javier\Desktop\xJavier\videos NDS\traducidos"
LOG_DIR = r"C:\Users\javier\Desktop\xJavier\videos NDS\logs"

# Si ya tenés OPENAI_API_KEY configurada en Windows, esto alcanza.
# Si no, usá: client = OpenAI(api_key="TU_API_KEY")
client = OpenAI()

MODEL = "gpt-4.1-mini"
GAP_MS = 20
MAX_FILES = 1          # para probar. Después poné None para todos.
WINDOW_SIZE = 3        # redistribución local
MAX_CHARS_PER_LINE = 42

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOG_PATH = os.path.join(
    LOG_DIR,
    f"tradusmart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

# =========================================================
# LOG
# =========================================================

def log(msg: str) -> None:
    print(msg)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# =========================================================
# TIME UTILS
# =========================================================

def parse_time_to_ms(t: str) -> int:
    t = t.replace(".", ",")
    hh, mm, rest = t.split(":")
    ss, ms = rest.split(",")
    return (
        int(hh) * 3600000
        + int(mm) * 60000
        + int(ss) * 1000
        + int(ms)
    )

def format_ms_to_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    hh = ms // 3600000
    ms %= 3600000
    mm = ms // 60000
    ms %= 60000
    ss = ms // 1000
    ms %= 1000
    return f"{hh:02}:{mm:02}:{ss:02},{ms:03}"

# =========================================================
# SRT PARSE / BUILD
# =========================================================

def parse_srt(content: str) -> list[dict]:
    content = content.replace("\ufeff", "").strip()
    chunks = re.split(r"\n\s*\n", content)

    entries = []
    for chunk in chunks:
        lines = [ln.rstrip() for ln in chunk.splitlines()]
        if len(lines) < 3:
            continue

        idx = lines[0].strip()
        time_line = lines[1].strip()

        if " --> " not in time_line:
            continue

        start, end = [x.strip() for x in time_line.split(" --> ", 1)]
        text = " ".join(ln.strip() for ln in lines[2:] if ln.strip())
        text = re.sub(r"\s+", " ", text).strip()

        entries.append({
            "idx": idx,
            "start": start.replace(".", ","),
            "end": end.replace(".", ","),
            "text": text,
        })

    return entries

def build_srt(entries: list[dict]) -> str:
    blocks = []
    for e in entries:
        blocks.append(f"{e['idx']}\n{e['start']} --> {e['end']}\n{e['text']}")
    return "\n\n".join(blocks) + "\n"

# =========================================================
# TIME REBUILD FROM ORIGINAL
# =========================================================

def rebuild_times_from_original(entries: list[dict], gap_ms: int = GAP_MS) -> list[dict]:
    rebuilt = []

    for i, e in enumerate(entries):
        new_entry = dict(e)
        start_ms = parse_time_to_ms(e["start"])

        if i < len(entries) - 1:
            next_start_ms = parse_time_to_ms(entries[i + 1]["start"])
            end_ms = next_start_ms - gap_ms
            if end_ms <= start_ms:
                end_ms = start_ms + 1
        else:
            end_ms = parse_time_to_ms(e["end"])
            if end_ms <= start_ms:
                end_ms = start_ms + 1

        new_entry["end"] = format_ms_to_time(end_ms)
        rebuilt.append(new_entry)

    return rebuilt

# =========================================================
# MODEL I/O
# =========================================================

def extract_output_text(response) -> str:
    parts = []
    for item in response.output:
        if getattr(item, "type", None) == "message":
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text":
                    parts.append(content.text)
    return "\n".join(parts).strip()

def translate_full_srt(original_srt_text: str) -> str:
    prompt = f"""
Traducí este archivo SRT completo al español.

CONTEXTO:
Video educativo de neurodinámica clínica.

OBJETIVO:
- español claro, natural y técnico
- menos literal
- más legible
- más corto cuando se pueda
- terminología clínica correcta

REGLAS OBLIGATORIAS:
1) Conservar EXACTAMENTE la numeración de bloques.
2) Conservar EXACTAMENTE los timestamps.
3) NO agregar comentarios ni explicaciones.
4) NO borrar bloques.
5) NO inventar contenido.
6) Podés reformular para que quede más claro y natural.
7) El texto debe sonar mejor que una traducción literal.

ARCHIVO SRT:
{original_srt_text}
""".strip()

    response = client.responses.create(
        model=MODEL,
        input=prompt
    )

    return extract_output_text(response)

# =========================================================
# TEXT / TOKEN HELPERS
# =========================================================

def clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def tokenize_preserve_quotes(text: str) -> list[str]:
    return clean_spaces(text).split()

def join_tokens(tokens: list[str]) -> str:
    return " ".join(tokens).strip()

def safe_truncate_words(tokens: list[str], max_chars: int) -> tuple[list[str], list[str]]:
    """
    Devuelve el mayor prefijo que entre en max_chars, sin cortar palabras.
    Si ninguna palabra entra, devuelve al menos la primera palabra completa.
    """
    if not tokens:
        return [], []

    current = []
    for i, tok in enumerate(tokens):
        candidate = join_tokens(current + [tok])
        if len(candidate) <= max_chars or not current:
            current.append(tok)
        else:
            return current, tokens[i:]

    return current, []

def rebalance_single_text_to_two_lines(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> str:
    text = clean_spaces(text)
    if not text:
        return text

    if len(text) <= max_chars:
        return text

    words = text.split()
    best_split = None
    target = len(text) / 2

    for i in range(1, len(words)):
        left = " ".join(words[:i]).strip()
        right = " ".join(words[i:]).strip()
        if not left or not right:
            continue
        score = abs(len(left) - len(right))
        penalty = 0

        # Penalizar líneas demasiado largas
        if len(left) > max_chars:
            penalty += (len(left) - max_chars) * 5
        if len(right) > max_chars:
            penalty += (len(right) - max_chars) * 5

        # Favorecer cortes en lugares naturales
        bonus = 0
        if left.endswith((",", ";", ":", ".")):
            bonus -= 6
        if words[i - 1].lower() in {"y", "e", "o", "u", "de", "del", "la", "el", "los", "las", "un", "una", "que", "con", "por", "para", "en"}:
            bonus += 5

        total = score + penalty + abs(len(left) - target) * 0.1 + bonus

        if best_split is None or total < best_split[0]:
            best_split = (total, left, right)

    if best_split:
        return f"{best_split[1]}\n{best_split[2]}"

    # fallback extremo
    left_tokens, right_tokens = safe_truncate_words(words, max_chars)
    if not right_tokens:
        return " ".join(left_tokens)
    return f"{' '.join(left_tokens)}\n{' '.join(right_tokens)}"

# =========================================================
# REDISTRIBUTION
# =========================================================

def get_block_capacity(block_text: str, duration_ms: int) -> int:
    """
    Capacidad aproximada por bloque.
    Base: proporcional a duración, con piso y techo razonables.
    """
    # velocidad aproximada conservadora de lectura para subtítulos
    chars_by_time = max(10, int(duration_ms / 55))   # ~18 chars por segundo aprox
    # si el texto original del bloque ya era corto, no forzar demasiado
    base = max(len(clean_spaces(block_text)), chars_by_time)
    return max(12, min(base, 95))

def choose_cut_index(words: list[str], target_chars: int, hard_limit_chars: int) -> int:
    """
    Elige dónde cortar sin partir palabras.
    Prioriza cercanía al target y cortes naturales.
    Devuelve cantidad de palabras para el bloque actual.
    """
    if not words:
        return 0

    candidates = []

    for i in range(1, len(words) + 1):
        left = " ".join(words[:i]).strip()
        left_len = len(left)

        if left_len > hard_limit_chars and i > 1:
            break

        score = abs(left_len - target_chars)

        last = words[i - 1]
        last_lower = last.lower().strip('",.?:;!¡¿')

        # Favorecer cierre natural
        if left.endswith((".", "!", "?", ",", ";", ":")):
            score -= 8

        # Favorecer antes de conectores de continuidad en lo que queda
        if i < len(words):
            nxt = words[i].lower().strip('",.?:;!¡¿')
            if nxt in {"y", "e", "o", "u", "pero", "aunque", "porque", "que", "cuando", "mientras", "si", "entonces"}:
                score += 3

        # Penalizar terminar en palabra colgante
        if last_lower in {"y", "e", "o", "u", "de", "del", "la", "el", "los", "las", "un", "una", "que", "con", "por", "para", "en"}:
            score += 6

        candidates.append((score, i))

    if not candidates:
        return 1

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]

def redistribute_window(window_entries: list[dict]) -> None:
    """
    Junta el texto ya traducido de la ventana y lo redistribuye entre esos bloques
    según duración/capacidad, sin cortar palabras.
    """
    if not window_entries:
        return

    all_text = clean_spaces(" ".join(e["text"].replace("\n", " ") for e in window_entries))
    all_words = tokenize_preserve_quotes(all_text)

    if not all_words:
        for e in window_entries:
            e["text"] = ""
        return

    durations = []
    capacities = []

    for e in window_entries:
        start_ms = parse_time_to_ms(e["start"])
        end_ms = parse_time_to_ms(e["end"])
        duration_ms = max(1, end_ms - start_ms)
        durations.append(duration_ms)
        capacities.append(get_block_capacity(e["text"], duration_ms))

    total_capacity = sum(capacities) if capacities else 1
    remaining_words = all_words[:]

    redistributed = []

    for idx, e in enumerate(window_entries):
        blocks_left = len(window_entries) - idx

        if blocks_left == 1:
            chunk_words = remaining_words
            redistributed.append(join_tokens(chunk_words))
            remaining_words = []
            break

        remaining_text = join_tokens(remaining_words)
        proportional_target = max(
            10,
            int(len(remaining_text) * (capacities[idx] / max(sum(capacities[idx:]), 1)))
        )
        hard_limit = max(proportional_target + 12, capacities[idx] + 12)

        cut_idx = choose_cut_index(remaining_words, proportional_target, hard_limit)

        # Asegurar que no vaciemos demasiado los siguientes bloques
        if len(remaining_words[cut_idx:]) < (blocks_left - 1):
            cut_idx = max(1, len(remaining_words) - (blocks_left - 1))

        chunk_words = remaining_words[:cut_idx]
        redistributed.append(join_tokens(chunk_words))
        remaining_words = remaining_words[cut_idx:]

    # Rebalanceo a dos líneas por bloque, sin cortar palabras
    for i, e in enumerate(window_entries):
        text = redistributed[i] if i < len(redistributed) else ""
        e["text"] = rebalance_single_text_to_two_lines(text, max_chars=MAX_CHARS_PER_LINE)

def redistribute_all(entries: list[dict], window_size: int = WINDOW_SIZE) -> list[dict]:
    """
    Redistribución en ventanas solapadas. Aplica localmente y avanza por ventanas.
    """
    result = [dict(e) for e in entries]

    i = 0
    while i < len(result):
        window = result[i:i + window_size]
        redistribute_window(window)
        i += window_size

    return result

# =========================================================
# PROCESS FILE
# =========================================================

def process_file(input_path: str, output_path: str) -> None:
    with open(input_path, "r", encoding="utf-8") as f:
        original_content = f.read()

    original_entries = parse_srt(original_content)
    if not original_entries:
        raise ValueError("No se pudieron leer bloques SRT válidos.")

    log(f"   Bloques: {len(original_entries)}")

    translated_srt = translate_full_srt(original_content)
    translated_entries = parse_srt(translated_srt)

    if len(translated_entries) != len(original_entries):
        raise ValueError(
            f"La traducción devolvió {len(translated_entries)} bloques y el original tiene {len(original_entries)}."
        )

    # Copiar SOLO textos traducidos al esqueleto original
    merged = []
    for orig, trans in zip(original_entries, translated_entries):
        merged.append({
            "idx": orig["idx"],
            "start": orig["start"],
            "end": orig["end"],
            "text": clean_spaces(trans["text"]),
        })

    # Reconstruir tiempos desde el original
    merged = rebuild_times_from_original(merged, gap_ms=GAP_MS)

    # Redistribuir localmente el texto ya traducido
    merged = redistribute_all(merged, window_size=WINDOW_SIZE)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(build_srt(merged))

# =========================================================
# MAIN
# =========================================================

def main() -> None:
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".srt")]
    files.sort()

    if not files:
        log("❌ No hay archivos .srt en paratraducir")
        return

    if MAX_FILES is not None:
        files = files[:MAX_FILES]

    log(f"🔁 Archivos a procesar: {len(files)}")
    log(f"🧠 Modelo: {MODEL}")
    log(f"⏱ Gap: {GAP_MS} ms")
    log(f"🪟 Ventana: {WINDOW_SIZE} bloques")
    log("")

    for i, filename in enumerate(files, start=1):
        input_path = os.path.join(INPUT_DIR, filename)
        output_name = filename.replace(".srt", "_es.srt")
        output_path = os.path.join(OUTPUT_DIR, output_name)

        log(f"[{i}/{len(files)}] {filename}")

        try:
            process_file(input_path, output_path)
            log(f"   ✅ OK -> {output_name}")
        except Exception as e:
            log(f"   ❌ Error -> {e}")

        log("")
        time.sleep(0.5)

    log("🎯 Proceso completado")

if __name__ == "__main__":
    main()