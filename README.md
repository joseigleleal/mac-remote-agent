# mac-remote-agent

Un agente que maneja tu Mac a distancia desde Telegram. Le escribes «hola mac, en mi perfil personal pon bad bunny
en spotify» (el saludo es opcional) y lo hace en tu Chrome, con tus sesiones ya iniciadas y en la pestaña que ya
tenías abierta. Lo que dices con otras palabras, o varias cosas a la vez («pon algo de salsa y déjalo bajito»), lo
resuelve un modelo local que decide qué acciones usar y en qué orden. También ve qué apps tienes abiertas y qué consume más, cierra apps, cambia el volumen y corre
comandos de una lista que tú defines. Los comandos también aparecen en el menú «/» de Telegram.

Además actúa por su cuenta en dos casos: **rutinas** (pedidos que le dejas programados, como «rutina lunes a viernes 8:00 qué está consumiendo más») y un **chequeo** cada 30 min de lo que necesita para funcionar (Ollama, permisos de macOS, eco, disco, sesiones vencidas). Si algo se rompe te avisa una vez y, si el arreglo es conocido y seguro, lo aplica solo.

> Antes de usarlo o adaptarlo, lee [Uso responsable](USO_RESPONSABLE.md): quien controla el bot controla la Mac.

| | |
|---|---|
| Tipo | Agente siempre encendido (long polling) con acciones de una lista cerrada: reglas en español para lo conocido y un modelo local (Ollama, `qwen3:8b`) con llamada a herramientas para el resto |
| Frecuencia | Responde al instante mientras la Mac esté despierta · chequeo propio cada `CHEQUEO_MIN` (30) min · rutinas a su hora |
| Entradas | Mensajes y botones de Telegram (solo de los chats autorizados) · Chrome (perfiles, ventanas y pestañas) |
| Salidas | Acciones en Chrome · respuestas por Telegram · `data/bot.log` |
| Consumo | ~20-30 MB de RAM y 0 % de CPU mientras espera (una conexión a Telegram que se renueva cada 50 s). Cuando usa el modelo: ~5 GB de RAM y la GPU unos segundos; se descarga de la memoria al minuto sin uso |

**Qué sabe hacer hoy**

| Pedido | Qué hace |
|---|---|
| «hola mac, qué perfiles hay» · `/perfiles` | Lista los perfiles de Chrome abiertos (los permitidos) |
| «hola mac, pon bad bunny en spotify» · `/spotify bad bunny` | Si no dices el perfil y hay varios abiertos, pregunta con botones. Busca en la pestaña de Spotify de ese perfil (sin recargarla) y reproduce el primer resultado; si no hay pestaña, la abre en ese perfil |
| «pausa spotify» · «sigue la música» · «siguiente canción» · «canción anterior» · `/musica pausa` | Controla la pestaña de Spotify que está sonando (busca en los perfiles abiertos, sin preguntar). «pausa» sola pausa el bot |
| «reautentica <sitio>» · «inicia sesión en <sitio>» · `/login <sitio>` | Si una pestaña del perfil quedó en la página de login (sesión vencida), rellena usuario (si está vacío) y clave del `.env` y continúa, paso a paso (confirmar cuenta → clave). Si queda en un segundo factor o captcha, avisa y no lo salta |
| «chats» · «exporta <nombre>» · «exporta 5» · «exporta recientes 50» · «excluye <nombre>» | WhatsApp de la Mac para entrenar tu «clon»: lista tus chats uno a uno con más mensajes tuyos y exporta **solo tus mensajes** (con el mensaje anterior del otro como contexto, sin teléfonos, correos ni enlaces) a `data/whatsapp/`: uno por nombre, varios al azar o los primeros de la lista de la app (los más recientes). Sin grupos; los excluidos nunca se exportan. Si macOS no da el permiso en 20 s, avisa cuál falta en vez de colgarse |
| «eco: <mensaje que te mandaron>» · «eco (Ana): …» · `/eco …` | Te sugiere cómo responderías tú, con tu forma de escribir aprendida de esos chats. Lo hace el agente `eco` de [personal-agents](https://github.com/joseigleleal/ai-personal-agents) (todo local, con Ollama); aquí solo se llama (`ECO_DIR`). Nunca envía nada |
| «rutina 8:00 qué está consumiendo más» · «rutina lunes a viernes 7:30 pon lofi en spotify» · «rutina fines de semana 10 chequeo» · «rutinas» · «borra rutina 2» · `/rutinas` | Programa un pedido para que lo haga solo cada día (o de lunes a viernes, o sábados y domingos) a esa hora. A su hora lo atiende como si se lo acabaras de escribir: mismas reglas, mismo agente y mismos controles. No acepta rutinas que apaguen o pausen el bot. Si la Mac dormía, corre al despertar si no pasó más de 1 h |
| «chequeo» · «revisa la mac» · `/chequeo` | Revisa Ollama, el permiso de Accesibilidad, la lectura de WhatsApp, eco, el disco libre y si alguna sesión de `LOGIN_SITIOS` venció. Lo mismo hace solo cada 30 min (ver «Chequeo y reparación» abajo) |
| «qué haces» · «qué dijiste» · `/claude` | Última acción y último mensaje de la sesión de Claude Code (lee el transcript) |
| «claude: …» · «avisos claude on / off» · `/avisos_claude` | Claude Code desde Telegram: a pedido (solo te llega la respuesta a lo que le escribes) o modo fuera (avisos de todo y preguntas con botones). Ver abajo |
| «abre youtube (en personal)» · «busca youtube» · `/abre …` | Abre la página (por nombre conocido, dirección o, si no, búsqueda en Google) en ese perfil; sin perfil, pregunta con botones. Reutiliza la pestaña si ya existe y queda como **la pestaña de la conversación** |
| «busca …» (con una página abierta) · «pon el primero» | Busca dentro de esa página (dirección de búsqueda del sitio o su buscador) y, en YouTube, reproduce el primer resultado. Sin página abierta en los últimos 30 min, «busca …» va a Spotify |
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

| Pedido libre | Qué hace |
|---|---|
| Cualquier frase que ninguna regla entiende, o varios pedidos juntos: «ponme algo de salsa y déjalo bajito, como a 20», «qué está consumiendo más? si es pycharm ciérralo», «abre youtube y pon el primero de lofi», «cómo le contesto a Ana que me dijo ¿vienes mañana?» | El modelo local elige las acciones (las mismas de esta tabla), las ejecuta una tras otra mirando cada resultado y se detiene si alguna pide confirmación con botones. Recuerda los últimos intercambios de 30 min («y ahora súbele») |

## Flujo

```
Telegram ──▶ bot.py (long polling) ──▶ ¿chat autorizado? no → se ignora
                                   └─▶ interprete.py: texto → acción de la lista (perfiles · volumen · spotify · ayuda)
                                          └─▶ ¿ninguna regla lo entendió? → agente.py: el modelo pide acciones de la
                                              lista una tras otra (resultado → siguiente) hasta terminar o pedir botones
                                          └─▶ ¿qué perfil? dicho en el texto · único abierto · si no, botones
                                                 └─▶ chrome.py: ventana del perfil → pestaña de Spotify
                                                        ├─ existe → spotify.py cambia a la búsqueda (sin recargar)
                                                        └─ no     → la abre en ese perfil
                                                     → clic en ▶ del primer resultado → ¿suena? → respuesta

Entre esperas a Telegram (como mucho cada ~50 s), por iniciativa propia y nunca en pausa:
   ├─ ¿pasaron CHEQUEO_MIN min? → chequeo.py: revisa → problema nuevo: ¿arreglo conocido? → lo intenta una vez
   │                                                   └─ si no: aviso (con botón si basta un toque, ej. iniciar sesión)
   │                              → problema que ya no está: «✅ resuelto»
   └─ ¿alguna rutina toca ahora? → su texto entra por el mismo camino que un mensaje tuyo (reglas → agente)
```

## Cómo funciona por dentro

### En palabras simples

El bot queda escuchando a Telegram. Cuando le escribes, primero mira que seas tú (solo obedece a los chats de la
lista). Después lee el pedido buscando palabras conocidas: si habla de perfiles, los lista; si habla de música,
saca qué buscar y en qué perfil. Nunca ejecuta lo que escribes como si fuera un comando: solo elige entre las
acciones que sabe hacer.

Si ninguna regla entiende el pedido, se lo pasa a un modelo de lenguaje que corre en la Mac. El modelo no puede
hacer nada por su cuenta: solo puede pedir las mismas acciones de la lista, y el bot las ejecuta con los mismos
controles. Así, «pon algo de salsa y déjalo bajito» se vuelve dos acciones (Spotify y volumen), y si una necesita
tu confirmación, se detiene ahí.

Para tocar Chrome usa AppleScript, la forma que tiene macOS de controlar apps. Con eso ve tus ventanas y pestañas
y puede ejecutar código en una página, como hacer clic en «play». El truco está en saber qué ventana es de qué
perfil: Chrome no lo dice, pero cada perfil guarda en un archivo las pestañas que tiene abiertas, así que el bot
compara y deduce de quién es cada ventana.

### Detalle técnico (para replicarlo)

**Archivos y piezas**

| Archivo | Qué hace | Funciones clave |
|---|---|---|
| `mac/bot.py` | Bucle de long polling, autorización, pregunta del perfil con botones y respuesta; entre esperas, el chequeo y las rutinas | `Bot.atender`, `Bot.spotify`, `Bot.boton`, `Bot.por_iniciativa`, `quien` |
| `mac/interprete.py` | Texto → `Pedido(accion, datos)` con reglas (sin tildes, quita «hola mac», el perfil y el «dale play») | `interpretar`, `consulta_musica` |
| `mac/agente.py` | Lo que ninguna regla entiende: ciclo con el modelo de Ollama y herramientas (cada una es una acción de la lista cerrada), memoria corta, sin resumen inventado al final | `atender`, `HERRAMIENTAS`, `ACCION`, `pedido`, `Memoria`, `cargado` |
| `mac/chrome.py` | Perfiles, perfiles abiertos, ventana de cada perfil, buscar pestaña, ejecutar JavaScript, abrir URL en un perfil | `perfiles`, `abiertos`, `resolver`, `ventanas`, `asignar_perfiles`, `buscar_pestana`, `ejecutar_js`, `abrir` |
| `mac/spotify.py` | Búsqueda y play en la web de Spotify, y los botones de la barra (play/pausa, siguiente, anterior) | `reproducir`, `controlar`, `sonando` |
| `mac/volumen.py` | Volumen y silencio de la Mac por AppleScript (`set volume`) | `estado`, `ajustar` |
| `mac/comandos.py` | Comandos de la lista permitida, sin shell, en segundo plano; registro en `data/comandos.json` para verlos y detenerlos | `ejecutar`, `detener`, `corriendo`, `resumen` |
| `mac/apps.py` | Apps abiertas (System Events, con bundle id), consumo por app (memoria de `top`, que incluye la de la GPU como el Monitor de Actividad; CPU de `ps`; agrupado por `/X.app/`) y cerrar por bundle id | `abiertas`, `consumo`, `resumen_mac`, `cerrar`, `buscar` |
| `mac/login.py` | Sitios de `LOGIN_*` en `.env`, pestaña de login por dominio, relleno genérico (setter nativo + eventos `input`/`change`), espera a que cada paso cargue y verifica en la misma pestaña; `--guardar` pide la clave sin mostrarla | `sitios`, `reautenticar`, `estado_pagina`, `guardar` |
| `mac/whatsapp.py` | Lee la base local de la app de WhatsApp (copia temporal, solo lectura): chats uno a uno, excluidos, pares (contexto, respuesta) limpios | `chats`, `pares`, `exportar`, `excluir` |
| `mac/eco.py` | Llama a la línea de comandos del agente `eco` (otro repo, su propio entorno) con el mensaje como argumento, sin shell y con tope de tiempo | `sugerir` |
| `mac/claude_puente.py` | Hooks `Stop` (avisa y espera tu mensaje; con mensaje, sale con código 2 y Claude Code despierta a Claude con él), `PreToolUse` de `AskUserQuestion` (opciones con botones → `updatedInput.answers`) y `Notification`; buzón en `data/claude/` que escribe el bot | `hook_stop`, `hook_pregunta`, `que_haces`, `dejar_mensaje` |
| `mac/claude_aviso.py` | Hook de Claude Code (eventos `Stop` y `Notification`): manda por Telegram el comienzo de la última respuesta o el aviso de que necesita permiso o una respuesta | `texto_aviso`, `ultima_respuesta` |
| `mac/web.py` | Sitios conocidos y sus búsquedas, abrir en un perfil (reutiliza la pestaña), buscar en la página (plantilla o buscador visible), primer video de YouTube | `abrir`, `buscar`, `primero`, `Contexto` |
| `mac/terminal.py` | Escribe un comando en una terminal visible: IDE de JetBrains con teclado simulado (Esc → ⌥F12 → ⌘T → comando → Enter) o iTerm por su AppleScript | `escribir` |
| `mac/chequeo.py` | Revisiones de la Mac (solo lo configurado), aviso una vez por problema y «resuelto» al desaparecer (estado en `data/chequeo.json`), arreglo automático de una lista cerrada (hoy: prender Ollama) una sola vez por problema | `revisar`, `vuelta`, `informe`, `toca`, `prender_ollama` |
| `mac/rutinas.py` | Rutinas en `data/rutinas.json`: entender «rutina <días> <hora> <pedido>», rechazar las prohibidas, decir cuáles tocan ahora (y marcarlas para no repetirlas) | `entender`, `agregar`, `pendientes`, `resumen`, `borrar` |
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

### Claude Code desde Telegram (a pedido o modo fuera)

Para seguir y guiar una sesión larga de Claude Code sin estar frente a la Mac. Hooks en `.claude/settings.local.json`
del proyecto (local, no se versiona), todos con `cd <este repo> && .venv/bin/python -m mac.claude_puente <modo>`:

| Hook | Modo | Qué hace |
|---|---|---|
| `Stop` (`"async": true, "asyncRewake": true`, timeout ~1900) | `stop` | Si el turno respondía a un mensaje tuyo de Telegram, te manda la respuesta entera (en modo fuera, además, el comienzo de cada respuesta). Luego espera hasta 30 min un mensaje tuyo («claude: …» o respondiendo a un mensaje suyo); si llega, Claude sigue trabajando con él |
| `PreToolUse`, matcher `AskUserQuestion` (timeout ~330) | `pregunta` | Las preguntas con opciones llegan con botones; tu elección vuelve como respuesta. Sin respuesta en 5 min, sale en la consola |
| `Notification` (`"async": true`) | `aviso` | Avisa que pide permiso o espera algo |

En el PC siempre ves todo; lo que va a Telegram depende del modo:
- **A pedido** (por defecto, «avisos claude off»): nada llega solo. «claude: …» le escribe a Claude y solo su
  respuesta a ese mensaje vuelve a Telegram; «qué haces» muestra lo último. Así no te duplica en el celular lo
  que ya ves en el PC.
- **Modo fuera** («avisos claude on»): para cuando no estás frente a la Mac. Avisa cada vez que Claude termina o
  pide permiso, y sus preguntas con opciones llegan con botones.

Los hooks nunca leen Telegram: lo hace el bot (solo de tu chat) y deja los mensajes en `data/claude/`.
Para ver la sesión completa o aprobar permisos, el control remoto de Claude Code (`/remote-control`).

### Chequeo y reparación

El bot es lo único que vigila la Mac (los servidores los vigila el agente `vigia` de
[personal-agents](https://github.com/joseigleleal/ai-personal-agents)). Cada `CHEQUEO_MIN` minutos revisa solo lo
que tienes configurado:

| Revisión | Cuándo aplica | Si falla |
|---|---|---|
| Ollama responde | `AGENTE_MODELO` con valor | **Lo prende solo** (app de Ollama o `brew services start ollama`), una vez; si no vuelve, avisa |
| Permiso de Accesibilidad | Siempre | Avisa con la ruta exacta de Python.app que hay que agregar (cambia si Homebrew actualiza Python) |
| Lectura de WhatsApp | Si ya exportaste chats (`data/whatsapp/`) | Avisa que falta «Acceso total al disco» (o un aviso de macOS pendiente) |
| eco | `ECO_DIR` con valor | Avisa si no está su Python o no puede leer su carpeta |
| Disco libre | Siempre | Avisa bajo `CHEQUEO_DISCO_MIN_GB` (10). Nunca borra nada |
| Sesiones vencidas | `LOGIN_SITIOS` con valor y Chrome abierto | Avisa con un botón «🔑 Iniciar sesión»: no entra solo, porque un login fallido repetido puede bloquear la cuenta |

Cada problema se avisa **una vez** (no en cada vuelta) y, cuando desaparece, llega «✅ resuelto». El arreglo
automático se intenta **una sola vez por problema**: si no funciona, avisa y espera a que lo resuelvas. Para probarlo
sin avisar ni reparar: `.venv/bin/python -m mac.chequeo`.

## Decisiones de diseño (y por qué)

- **Lista cerrada de acciones:** un bot que ejecuta lo que le escriben es una puerta a la Mac para quien consiga
  el token. Aquí el texto solo elige entre acciones conocidas.
- **Usar la pestaña que ya está abierta:** ahí ya iniciaste sesión, y una página que ya tocaste puede reproducir
  audio; una pestaña nueva abierta por un programa a veces no.
- **Perfil por archivo de sesión:** AppleScript no expone el perfil de una ventana. Leer el título por
  Accesibilidad exige otro permiso y depende del idioma; el archivo de sesión ya está ahí y solo se lee.
- **Reglas primero, modelo después:** lo conocido lo resuelven reglas instantáneas, gratis y probadas; el modelo
  solo entra cuando ninguna entiende el pedido o hay varios pasos.
- **El modelo elige, el bot ejecuta:** cada herramienta del modelo es una acción de la lista cerrada; no hay una
  herramienta para ejecutar texto libre ni para apagar el bot. Si el modelo pone un perfil que no dijiste, se
  descarta (y el bot pregunta con botones). Si usó herramientas, no se manda su resumen final: los resultados
  ya te llegaron y un resumen solo agrega la chance de inventar («la factura está en tu bandeja»).
- **Modelo local:** `qwen3:8b` en Ollama sabe llamar herramientas, entiende bien el español y nada sale de la Mac.
  Se descarga de la memoria a 1 min sin uso (`AGENTE_KEEP_ALIVE`): en espera no ocupa RAM; a cambio, el primer
  pedido tras un rato tarda ~35 s en cargarlo (después, 5-15 s).
- **El último mensaje atendido se guarda en disco** (`data/offset`) antes de actuar: si una acción tumba el bot
  (apagar) o launchd lo reinicia, al volver no repite el mismo mensaje ni el mismo botón.
- **Long polling y no webhook:** no hace falta abrir puertos ni un servidor público; la Mac pregunta a Telegram.
- **Comandos solo de una lista exacta, sin shell:** «ejecuta X» por Telegram es lo más riesgoso del bot. Solo
  corre lo que está tal cual en `COMANDOS_PERMITIDOS`, con `shlex.split` y sin shell (no hay `|`, `;` ni `&&` que
  colar). Por defecto corre en segundo plano (no depende de que el IDE esté abierto); en una terminal visible solo si
  se pide, y siempre en una pestaña nueva, porque no hay forma confiable de saber qué terminal está libre.
- **Autonomía con la misma lista cerrada:** las rutinas no son acciones nuevas, son pedidos tuyos con hora; pasan por
  el mismo camino que un mensaje, así que no pueden hacer nada que no podrías pedir tú (y no pueden apagar ni pausar
  el bot). El chequeo solo repara lo que tiene un arreglo conocido, inofensivo y reversible (prender Ollama); lo que
  depende de ti (permisos, borrar archivos, iniciar sesión) lo avisa con los pasos o un botón.
- **Avisar una vez, reparar una vez:** un aviso que se repite cada 30 min se termina ignorando, y una reparación que
  se reintenta en bucle puede empeorar las cosas. Por eso el estado de cada problema se guarda en disco.
- **El chequeo vive en el bot, no en otro servicio:** el bot ya está despierto y escuchando; mirar el reloj entre
  esperas a Telegram no cuesta nada y evita otro proceso de launchd.
- **Login con datos del `.env`, con cuidado:** la clave queda en texto plano (el `.env` con permisos 600). Nunca va a
  Telegram ni al log, ni como argumento de un proceso (se vería con `ps`): viaja a Chrome dentro del script que
  `osascript` lee por la entrada estándar. Si un intento falla, no reintenta: varios fallos pueden bloquear la cuenta.
  Más seguro sería el Llavero de macOS; aquí se eligió el `.env` por simplicidad.
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
- Las reglas entienden frases parecidas a los ejemplos; una frase muy distinta va al modelo, que es más lento y se
  puede equivocar de acción (las delicadas igual piden confirmación). Sin Ollama, cae en la ayuda.
- Un modelo de 8B necesita ~5 GB de RAM libres mientras responde; con 8 GB de RAM en total conviene `qwen3:4b`.
- El perfil de una ventana se deduce de su archivo de sesión: una ventana recién abierta puede tardar unos
  segundos en reconocerse.

## Licencia

[MIT](LICENSE): puedes usarlo, copiarlo y adaptarlo, también con fines comerciales, manteniendo el aviso de
licencia. Se entrega sin garantía; el uso debe respetar las reglas de [Uso responsable](USO_RESPONSABLE.md).
