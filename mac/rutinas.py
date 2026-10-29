"""Rutinas: pedidos que el bot hace solo a una hora, sin que se los escribas («rutina 8:00 qué está consumiendo más»).

Una rutina es el texto de un pedido normal más una hora y unos días. A su hora, el bot lo atiende como si lo
acabaras de escribir: pasa por las mismas reglas, el mismo agente y los mismos controles (perfiles permitidos,
comandos de la lista, botones para lo delicado). No amplía lo que el bot puede hacer: solo cuándo lo hace.

- No se aceptan rutinas que apaguen o pausen el bot ni que creen otras rutinas.
- Si la Mac estaba dormida a esa hora, la rutina corre al despertar si no pasó más de VENTANA_MIN; si pasó más, se
  salta ese día (una rutina de las 8 no debe sonar a mediodía).
- Se guardan en data/rutinas.json.
"""
import json
import re
from datetime import datetime

from mac.config import DATA_DIR
from mac.interprete import interpretar, normalizar

ARCHIVO = DATA_DIR / "rutinas.json"
VENTANA_MIN = 60
DIAS = {"todos": "todos los días", "habiles": "de lunes a viernes", "finde": "sábados y domingos"}
PROHIBIDAS = ("apagar", "pausar", "reanudar", "rutina", "rutinas", "borra_rutina")

PATRON = re.compile(
    r"^/?rutinas?\s+(?P<dias>todos los d[ií]as\s+|diaria(?:mente)?\s+|(?:de\s+)?lunes a viernes\s+|d[ií]as h[aá]biles\s+|"
    r"(?:los\s+)?fines? de semana\s+)?(?:a las\s+)?(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?:h|hrs|horas)?\s*[:,-]?\s+"
    r"(?P<texto>.+)$", re.I | re.S)


def leer() -> list[dict]:
    try:
        return json.loads(ARCHIVO.read_text())
    except (OSError, ValueError):
        return []


def guardar(rutinas: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ARCHIVO.write_text(json.dumps(rutinas, ensure_ascii=False, indent=1))


def entender(texto: str) -> dict | None:
    """«rutina lunes a viernes 7:30 pon lofi en spotify» → {hora: "07:30", dias: "habiles", texto: "pon lofi…"}."""
    m = PATRON.match(texto.strip())
    if not m:
        return None
    h, mi = int(m.group("h")), int(m.group("m") or 0)
    if h > 23 or mi > 59:
        return None
    dias = normalizar(m.group("dias") or "")
    clase = "habiles" if "viernes" in dias or "habiles" in dias else "finde" if "semana" in dias else "todos"
    return {"hora": f"{h:02d}:{mi:02d}", "dias": clase, "texto": m.group("texto").strip()}


def agregar(texto: str, hay_modelo: bool) -> str:
    rutina = entender(texto)
    if not rutina:
        return ("No entendí la rutina. Así: «rutina 8:00 qué está consumiendo más» o «rutina lunes a viernes 7:30 "
                "pon lofi en spotify».")
    accion = interpretar(rutina["texto"]).accion
    if accion in PROHIBIDAS:
        return "Esa no la programo: una rutina no puede apagar ni pausar el bot, ni crear otras rutinas."
    if accion == "ayuda" and not hay_modelo:
        return f"No entiendo «{rutina['texto']}» como pedido, así que no lo programo. Escríbelo como me lo pedirías."
    rutinas = leer()
    rutina["id"] = max((r["id"] for r in rutinas), default=0) + 1
    rutinas.append(rutina)
    guardar(rutinas)
    return f"⏰ Rutina {rutina['id']}: {DIAS[rutina['dias']]} a las {rutina['hora']} haré «{rutina['texto']}»."


def borrar(numero: int) -> str:
    rutinas = leer()
    quedan = [r for r in rutinas if r["id"] != numero]
    if len(quedan) == len(rutinas):
        return f"No hay una rutina {numero}. Dime «rutinas» para verlas."
    guardar(quedan)
    return f"🗑️ Rutina {numero} borrada."


def resumen() -> str:
    rutinas = leer()
    if not rutinas:
        return ("No hay rutinas. Crea una: «rutina 8:00 qué está consumiendo más» (también «lunes a viernes» o "
                "«fines de semana» antes de la hora).")
    return "⏰ Rutinas:\n" + "\n".join(f"{r['id']}. {DIAS[r['dias']]} a las {r['hora']}: «{r['texto']}»"
                                       for r in sorted(rutinas, key=lambda r: r["hora"])) + \
        "\n\nPara quitar una: «borra rutina <número>»."


def toca_hoy(rutina: dict, ahora: datetime) -> bool:
    return rutina["dias"] == "todos" or (rutina["dias"] == "habiles") == (ahora.weekday() < 5)


def pendientes(ahora: datetime | None = None) -> list[dict]:
    """Las rutinas que tocan ahora (y las marca como hechas hoy, para no repetirlas aunque el bot se reinicie)."""
    ahora = ahora or datetime.now()
    hoy = ahora.date().isoformat()
    rutinas, salida = leer(), []
    for r in rutinas:
        h, m = map(int, r["hora"].split(":"))
        atraso = (ahora - ahora.replace(hour=h, minute=m, second=0, microsecond=0)).total_seconds() / 60
        if r.get("ultima") != hoy and toca_hoy(r, ahora) and 0 <= atraso < VENTANA_MIN:
            r["ultima"] = hoy
            salida.append(r)
    if salida:
        guardar(rutinas)
    return salida
