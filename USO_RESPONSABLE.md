# Uso responsable

Este proyecto permite controlar una Mac desde Telegram: abrir y usar el navegador con tus sesiones iniciadas,
reproducir música y, más adelante, otras tareas. Eso es útil y también delicado, porque quien controle el bot
controla lo que esa Mac puede hacer. Antes de usarlo o adaptarlo, lee estas reglas.

## Para qué es

- Automatizar **tu propia** Mac, con **tus propias** cuentas, para tareas tuyas.
- Aprender y experimentar con agentes que actúan sobre un equipo real.

## Qué no se debe hacer

- **Controlar un equipo o una cuenta que no son tuyos** sin permiso expreso y por escrito de su dueño.
- **Usar cuentas o sistemas de un empleador o cliente** sin su autorización, ni sacar su información fuera de
  los canales que ellos aprueban (los mensajes del bot pasan por Telegram).
- **Hacerse pasar por otra persona** o mandar mensajes en nombre de alguien sin que lo sepa.
- **Saltarse los términos de un servicio**: evadir captchas, límites de uso o bloqueos, o automatizar donde el
  sitio lo prohíbe.
- **Guardar o usar credenciales ajenas**, o de un empleador sin su autorización, para el inicio de sesión
  automático. Y ten presente que si una organización hace vencer la sesión cada cierto tiempo, es una medida de
  seguridad suya.
- **Leer o exportar chats de WhatsApp de otra persona**, o usar los tuyos para algo distinto de aprender tu propio
  estilo. Aun siendo tuyos, contienen mensajes de terceros: por eso solo se guarda el mensaje anterior como contexto,
  se quitan teléfonos y correos, y todo queda en tu Mac.
- **Mover dinero**: pagos, compras o transferencias. El bot no tiene ni debe tener esas acciones.
- **Vigilar a otras personas**: leer sus chats, correos o pantallas, o juntar sus datos.
- **Mandar spam** o usar el bot para molestar a terceros.

## Seguridad mínima

- **El bot solo obedece a los chats de `TELEGRAM_CHAT_ID`.** Si está vacío, no obedece a nadie. Nunca lo dejes
  abierto a cualquiera.
- **El token es la llave de tu Mac.** Va solo en `.env` (fuera de git). Si se filtra: @BotFather → `/revoke`, y
  pon el nuevo en `.env`.
- **Solo acciones de una lista cerrada.** El texto que llega por Telegram nunca se ejecuta como comando: se
  interpreta y se elige una acción conocida. Al agregar acciones, mantén esa regla.
- **El modelo no amplía lo que el bot puede hacer.** Lo que ninguna regla entiende lo decide un modelo local, pero
  solo puede pedir acciones de la misma lista, con los mismos controles. Un modelo se puede equivocar o ser engañado
  por un texto: por eso no tiene herramientas para ejecutar texto libre ni para nada irreversible sin confirmación.
- **Lo que hace por su cuenta también está acotado.** Las rutinas son pedidos tuyos con hora: pasan por los
  mismos controles que un mensaje y no pueden apagar ni pausar el bot. El chequeo solo repara solo lo inofensivo
  (prender Ollama), una vez; nunca borra archivos ni inicia sesión sin que toques el botón. Revisa de vez en cuando
  tus rutinas («rutinas»): una rutina olvidada sigue actuando en tu nombre.
- **Perfiles permitidos.** Con `CHROME_PERFILES_PERMITIDOS` deja fuera los perfiles que el bot no debe tocar
  (por ejemplo, el del trabajo).
- **Mac con contraseña y bloqueo de pantalla.** El bot actúa con tu sesión abierta.

## Privacidad

- Lo que le pides al bot y lo que te responde pasa por los servidores de Telegram.
- En el equipo solo se guardan logs en `data/` (fuera de git). No se guardan contraseñas ni contenido de las
  páginas.

## Sin garantía

Se comparte como ejemplo, tal cual, sin garantía de ningún tipo. Cada persona es responsable de cómo lo usa y de
cumplir las leyes y los términos de los servicios que automatice.
