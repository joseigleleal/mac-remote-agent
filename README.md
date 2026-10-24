# mac-remote-agent

Un agente que maneja tu Mac a distancia desde Telegram. Le escribes «hola mac, en mi perfil personal pon bad bunny
en spotify» (el saludo es opcional) y lo hace en tu Chrome, con tus sesiones ya iniciadas y en la pestaña que ya
tenías abierta. También ve qué apps tienes abiertas y qué consume más, cierra apps, cambia el volumen y corre
comandos de una lista que tú defines. Los comandos también aparecen en el menú «/» de Telegram.

> Antes de usarlo o adaptarlo, lee [Uso responsable](USO_RESPONSABLE.md): quien controla el bot controla la Mac.

| | |
|---|---|
| Tipo | Bot siempre encendido (long polling) con acciones de una lista cerrada; reglas en español, sin modelo de lenguaje |
| Frecuencia | Responde al instante mientras la Mac esté despierta |
| Entradas | Mensajes y botones de Telegram (solo de los chats autorizados) · Chrome (perfiles, ventanas y pestañas) |
| Salidas | Acciones en Chrome · respuestas por Telegram · `data/bot.log` |
| Consumo | ~20-30 MB de RAM y 0 % de CPU mientras espera (una conexión a Telegram que se renueva cada 50 s); algo de CPU solo los segundos en que atiende un pedido |

**Qué sabe hacer hoy**

| Pedido | Qué hace |
|---|---|
| «hola mac, qué perfiles hay» · `/perfiles` | Lista los perfiles de Chrome abiertos (los permitidos) |
| «hola mac, pon bad bunny en spotify» · `/spotify bad bunny` | Si no dices el perfil y hay varios abiertos, pregunta con botones. Busca en la pestaña de Spotify de ese perfil (sin recargarla) y reproduce el primer resultado; si no hay pestaña, la abre en ese perfil |
| «hola mac, en mi perfil personal …» | Usa ese perfil (por su apodo en `.env`, su nombre o su carpeta) |
| «sube el volumen» · «baja el volumen 20» · «volumen al 30» · «silencia» · «quita el silencio» · `/volumen 50` | Cambia el volumen de la Mac (de a 10 si no se dice cuánto) y dice cómo quedó |

| «ejecuta caffeinate -d» · `/ejecutar …` | Solo si el comando está **exacto** en `COMANDOS_PERMITIDOS` (`.env`). Corre sin shell y en segundo plano: no depende de una terminal ni del IDE. Si termina en 3 s devuelve su salida |
| «ejecuta caffeinate -d en la terminal de pycharm» (o «en intellij», «en iterm») | El mismo comando permitido, pero escrito en una pestaña **nueva** de la terminal de ese programa, para verlo correr |
| «detén caffeinate» · «qué comandos hay» · `/comandos` | Detiene los comandos que lanzó el bot y lista los permitidos y los que corren |
| «qué apps tengo abiertas» · `/apps` | Las apps abiertas y lo que más consume |
| «qué está consumiendo más» · `/consumo` | Carga y RAM libre de la Mac, y las apps que más RAM y CPU usan (los ayudantes cuentan con su app: Chrome incluye sus pestañas) |
| «cierra pycharm» · `/cerrar …` | Pregunta con botón y la cierra como ⌘Q (si hay algo sin guardar, la app lo pregunta en la Mac). Después vuelve a medir el consumo. Finder, Dock y `APPS_PROTEGIDAS` no se cierran |
| «cuánto consumes» · `/estado` | CPU, RAM y tiempo encendido del bot, y cómo está la Mac |
| «pausa» · «prende» · `/pausar` · `/reanudar` | Pausa: sigue escuchando pero no hace nada (salvo estado y prender) hasta «prende». Sobrevive a reinicios |
| «apágate del todo» · `/apagar` | Pide confirmación con botón y se baja de launchd. Ya no escucha: se vuelve a prender desde la Mac |

El «hola mac» es opcional: «pon bad bunny en spotify» funciona igual.

## Flujo

```
Telegram ──▶ bot.py (long polling) ──▶ ¿chat autorizado? no → se ignora
                                   └─▶ interprete.py: texto → acción de la lista (perfiles · volumen · spotify · ayuda)
                                          └─▶ ¿qué perfil? dicho en el texto · único abierto · si no, botones
                                                 └─▶ chrome.py: ventana del perfil → pestaña de Spotify
                                                        ├─ existe → spotify.py cambia a la búsqueda (sin recargar)
                                                        └─ no     → la abre en ese perfil
                                                     → clic en ▶ del primer resultado → ¿suena? → respuesta
```

## Cómo funciona por dentro

### En palabras simples

El bot queda escuchando a Telegram. Cuando le escribes, primero mira que seas tú (solo obedece a los chats de la
lista). Después lee el pedido buscando palabras conocidas: si habla de perfiles, los lista; si habla de música,
saca qué buscar y en qué perfil. Nunca ejecuta lo que escribes como si fuera un comando: solo elige entre las
acciones que sabe hacer.

Para tocar Chrome usa AppleScript, la forma que tiene macOS de controlar apps. Con eso ve tus ventanas y pestañas
y puede ejecutar código en una página, como hacer clic en «play». El truco está en saber qué ventana es de qué
perfil: Chrome no lo dice, pero cada perfil guarda en un archivo las pestañas que tiene abiertas, así que el bot
compara y deduce de quién es cada ventana.

### Detalle técnico (para replicarlo)

**Archivos y piezas**

| Archivo | Qué hace | Funciones clave |
|---|---|---|
| `mac/bot.py` | Bucle de long polling, autorización, pregunta del perfil con botones y respuesta | `Bot.atender`, `Bot.spotify`, `Bot.boton`, `quien` |
| `mac/interprete.py` | Texto → `Pedido(accion, datos)` con reglas (sin tildes, quita «hola mac», el perfil y el «dale play») | `interpretar`, `consulta_musica` |
| `mac/chrome.py` | Perfiles, perfiles abiertos, ventana de cada perfil, buscar pestaña, ejecutar JavaScript, abrir URL en un perfil | `perfiles`, `abiertos`, `resolver`, `ventanas`, `asignar_perfiles`, `buscar_pestana`, `ejecutar_js`, `abrir` |
| `mac/spotify.py` | Búsqueda y play en la web de Spotify | `reproducir`, `sonando` |
| `mac/volumen.py` | Volumen y silencio de la Mac por AppleScript (`set volume`) | `estado`, `ajustar` |
| `mac/comandos.py` | Comandos de la lista permitida, sin shell, en segundo plano; registro en `data/comandos.json` para verlos y detenerlos | `ejecutar`, `detener`, `corriendo`, `resumen` |
| `mac/apps.py` | Apps abiertas (System Events, con bundle id), consumo por app (`ps` agrupado por `/X.app/`) y cerrar por bundle id | `abiertas`, `consumo`, `resumen_mac`, `cerrar`, `buscar` |
| `mac/terminal.py` | Escribe un comando en una terminal visible: IDE de JetBrains con teclado simulado (Esc → ⌥F12 → ⌘T → comando → Enter) o iTerm por su AppleScript | `escribir` |
| `mac/servicio.py` | Consumo (`ps`, `memory_pressure`), pausa (archivo `data/pausado`) y apagado total (`launchctl disable` + `bootout`) | `recursos`, `pausar`, `reanudar`, `apagar` |
| `scripts/bot.sh` | Prender, apagar, reiniciar, estado y log desde la Mac | `prender`, `apagar`, `reiniciar`, `estado`, `log` |
| `mac/telegram.py` | Cliente mínimo de la API de bots | `actualizaciones`, `enviar`, `editar`, `teclado` |
| `mac/config.py` | `.env`, rutas y apodos de perfiles | `env`, `lista`, `alias_perfiles` |
| `scripts/instalar_launchd.sh` | Lo deja corriendo siempre (arranca con la sesión, se relanza si se cae) | `desinstalar` para quitarlo |
| `scripts/hooks/pre-commit` | Frena commits con secretos o datos personales | Patrones extra en `.secret-patterns` (local) |

**Un pedido, paso a paso**

1. `telegram.actualizaciones` espera hasta 50 s por mensajes nuevos (`getUpdates` con `timeout`): sin CPU mientras
   espera. Cada update avanza el `offset` aunque se ignore.
2. `autorizado`: el chat tiene que estar en `TELEGRAM_CHAT_ID`. Si no, ni se responde.
3. `interpretar` normaliza (minúsculas, sin tildes, sin «hola mac») y elige la acción. Para música toma lo que
   sigue al primer verbo («pon», «busca», «reproduce», «dale play a»…) y le quita el perfil, «en spotify» y el
   «y dale play» del final.
4. Perfil: `chrome.resolver` busca en el texto un apodo de `CHROME_PERFILES`, una carpeta o un nombre único. Si no
   hay y está abierto un solo perfil, usa ese; si hay varios, guarda el pedido y manda botones `perfil:<carpeta>`.
5. Perfiles abiertos: `lsof` del proceso de Chrome, buscando sus carpetas `Default` / `Profile N`. Se filtran con
   `CHROME_PERFILES_PERMITIDOS`.
6. Ventana de cada perfil: AppleScript lista ventanas y URLs; `asignar_perfiles` cuenta cuántas de esas URLs
   aparecen en el último `Sessions/Session_*` de cada perfil y se queda con el que más tiene.
7. `spotify.reproducir`: con pestaña, `history.pushState` + `popstate` lleva a `/search/<consulta>` sin recargar
   (la página conserva la interacción previa y Chrome la deja sonar); sin pestaña, `open -na "Google Chrome"
   --args --profile-directory=<carpeta> <url>`. Luego espera a que cambie el primer resultado (los nuevos tardan en reemplazar a los viejos), hace
   clic en su `button[data-testid="play-button"]` y confirma que suena otra canción leyendo la barra inferior.
8. Los datos van a AppleScript como argumentos (`on run argv`) y a JavaScript con `json.dumps`: el texto de
   Telegram nunca se pega dentro del código.

**Para replicarlo**

1. Python 3.12 o más: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
2. `cp .env.example .env`, crea el bot (abajo) y completa.
3. `.venv/bin/python -m mac.chrome` muestra tus perfiles (carpeta y nombre) para armar `CHROME_PERFILES`.
4. Prueba en primer plano: `.venv/bin/python -m mac.bot`. Luego `./scripts/instalar_launchd.sh`.
5. `git config core.hooksPath scripts/hooks` si vas a publicar cambios.

### Adaptarlo a tu caso

- **Otra acción:** agrégala a `ACCIONES` y a `interpretar`, escribe su módulo (como `spotify.py`) y su rama en
  `Bot.mensaje`. Mantén la regla: lista cerrada, datos como argumentos, nada del texto ejecutado tal cual.
- **Otra web en una pestaña existente:** `chrome.buscar_pestana(carpeta, "<dominio>")` + `chrome.ejecutar_js`.
  Los selectores de cada sitio cambian con el tiempo: búscalos con las herramientas de desarrollador.
- **Otro navegador basado en Chromium** (Brave, Edge): cambia `APP` y `CHROME_DIR`; el AppleScript es el mismo.
- **Lenguaje natural más libre:** reemplaza `interpretar` por un modelo que devuelva el mismo `Pedido` (JSON con
  una acción de la lista). El resto no cambia.

## Decisiones de diseño (y por qué)

- **Lista cerrada de acciones:** un bot que ejecuta lo que le escriben es una puerta a la Mac para quien consiga
  el token. Aquí el texto solo elige entre acciones conocidas.
- **Usar la pestaña que ya está abierta:** ahí ya iniciaste sesión, y una página que ya tocaste puede reproducir
  audio; una pestaña nueva abierta por un programa a veces no.
- **Perfil por archivo de sesión:** AppleScript no expone el perfil de una ventana. Leer el título por
  Accesibilidad exige otro permiso y depende del idioma; el archivo de sesión ya está ahí y solo se lee.
- **Reglas antes que un modelo:** para pocas acciones, unas reglas son instantáneas, gratis, sin red y se
  prueban. Un modelo tiene sentido cuando las acciones crezcan.
- **El último mensaje atendido se guarda en disco** (`data/offset`) antes de actuar: si una acción tumba el bot
  (apagar) o launchd lo reinicia, al volver no repite el mismo mensaje ni el mismo botón.
- **Long polling y no webhook:** no hace falta abrir puertos ni un servidor público; la Mac pregunta a Telegram.
- **Comandos solo de una lista exacta, sin shell:** «ejecuta X» por Telegram es lo más riesgoso del bot. Solo
  corre lo que está tal cual en `COMANDOS_PERMITIDOS`, con `shlex.split` y sin shell (no hay `|`, `;` ni `&&` que
  colar). Por defecto corre en segundo plano (no depende de que el IDE esté abierto); en una terminal visible solo si
  se pide, y siempre en una pestaña nueva, porque no hay forma confiable de saber qué terminal está libre.
- **Pausa además de apagado:** apagado, el bot ya no escucha Telegram y no podría prenderse desde ahí. La pausa
  deja la conexión abierta (casi sin costo) para poder volver con un mensaje.
- **Perfiles permitidos:** un perfil del trabajo o con datos sensibles se deja fuera en `.env`, sin tocar código.

## Uso

**Crear el bot y autorizarte**

1. En Telegram, **@BotFather** → `/newbot` → nombre y usuario (termina en `bot`) → copia el token a
   `TELEGRAM_BOT_TOKEN`.
2. Escríbele cualquier cosa a tu bot y corre `.venv/bin/python -m mac.bot --quien`: muestra tu `chat_id`. Ponlo
   en `TELEGRAM_CHAT_ID`.

**Permisos de la Mac (una vez)**

- **Automatización:** la primera vez que el bot toque Chrome, macOS pregunta si la app que lo corre (Terminal o
  Python) puede controlar «Google Chrome» → Permitir. Se cambia en Ajustes → Privacidad y seguridad → Automatización.
- **Accesibilidad** (solo para escribir en la terminal de PyCharm o IntelliJ): Ajustes → Privacidad y seguridad →
  Accesibilidad → «+» → la app de Python que corre el bot (`⌘⇧G` y la ruta de `Python.app` dentro de la instalación
  de Python). Si Python se actualiza, la ruta cambia y hay que darlo de nuevo.
- **JavaScript desde Apple Events:** en Chrome, en **cada perfil** que vaya a usar el bot: Ver → Opciones para
  desarrolladores → Permitir JavaScript desde Eventos de Apple. Sin esto puede abrir pestañas pero no hacer clic.
- **Que no se duerma:** el bot no responde con la Mac dormida. Ajustes → Batería → Opciones → «Evitar el reposo
  automático con el adaptador de corriente cuando la pantalla está apagada». Una portátil con la tapa cerrada se
  duerme igual (salvo con monitor externo).

```bash
.venv/bin/python -m mac.chrome            # perfiles, cuáles están abiertos y sus ventanas
.venv/bin/python -m mac.bot               # el bot en primer plano (Ctrl+C para salir)
./scripts/instalar_launchd.sh             # el bot siempre encendido · «desinstalar» para quitarlo
./scripts/bot.sh estado                   # ¿prendido? CPU, RAM y si está en pausa
./scripts/bot.sh apagar                   # apagado total (tampoco arranca al iniciar sesión)
./scripts/bot.sh prender                  # volver a prenderlo · «reiniciar» para tomar cambios del código o .env
./scripts/bot.sh log                      # qué está haciendo, en vivo
.venv/bin/python -m unittest discover tests
```

## Límites

- Solo macOS y Chrome (o derivados de Chromium), y la Mac tiene que estar despierta con la sesión abierta.
- Si Spotify cambia su web, los selectores de `spotify.py` pueden dejar de funcionar.
- Una pestaña abierta recién por el bot puede no reproducir hasta que la toques una vez (política de audio de Chrome).
- Las reglas entienden frases parecidas a los ejemplos; una frase muy distinta cae en la ayuda.
- El perfil de una ventana se deduce de su archivo de sesión: una ventana recién abierta puede tardar unos
  segundos en reconocerse.

## Licencia

[MIT](LICENSE): puedes usarlo, copiarlo y adaptarlo, también con fines comerciales, manteniendo el aviso de
licencia. Se entrega sin garantía; el uso debe respetar las reglas de [Uso responsable](USO_RESPONSABLE.md).
