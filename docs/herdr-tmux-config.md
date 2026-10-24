# Configuración de Herdr con tmux para adaptar a otro servidor

Configuración verificada el 20 de octubre de 2026, auditada de forma independiente el mismo día (19 pruebas aisladas superadas, ver [Verificaciones realizadas](#verificaciones-realizadas)) y revisada por segunda vez el 24 de octubre de 2026 con una auditoría de Codex (gpt-6-astra). El objetivo es mantener tmux como entorno exterior y usar Herdr para organizar terminales y agentes, con navegación, divisiones, scroll y copia similares a los de tmux.

La distribución de controles es:

- **tmux usa `Ctrl+b`.**
- **Herdr usa `Ctrl+a`, una sola vez por acción.** `Ctrl+a` → `Ctrl+a` envía un `Ctrl+a` literal (inicio de línea en zsh y en Claude Code).
- El mouse y la rueda llegan a Herdr cuando este los solicita.
- Los shells abiertos por Herdr no inician otro tmux automáticamente.
- Claude Code y Codex deben ejecutarse directamente en paneles de Herdr para que este los detecte.

Este archivo contiene los ajustes activos, instrucciones de uso y criterios para adaptarlos al servidor de destino. Los bloques de configuración son una referencia para integrar con los archivos existentes; no requieren reemplazar toda la configuración del servidor.

## Cambios de las auditorías

20 de octubre:

- `delivery = "system"` pasó a `delivery = "herdr"`: en este WSL `system` no mostraba ningún aviso (ver la sección de Herdr).
- La rueda en el modo de copia de tmux desplaza 3 líneas por paso (`-N 3`), igual que Herdr; antes desplazaba 1.
- Se corrigió la descripción de las recargas: `herdr server reload-config` aplica los atajos en todos los clientes.
- Se documentaron el prefijo literal, los cierres sin confirmación, la regla de OSC 52 por SSH y las pruebas reproducibles de `~/herdr-tmux-audit/`.

24 de octubre (segunda revisión, con una auditoría independiente de Codex gpt-6-astra; informe local en `~/herdr-tmux-audit/codex-audit-2026-10-24.md`, excluido del repositorio):

- `.zshrc`: el inicio automático reintenta con el número siguiente cuando dos shells arrancan a la vez («duplicate session») y exige un terminal real (`[[ -t 1 ]]`).
- `.tmux.conf`: `default-terminal` cae a `screen-256color` si falta la entrada terminfo de `tmux-256color`; el prefijo `Ctrl+b` y `prefix2 None` quedan declarados de forma explícita.
- `~/dotfiles`: `bootstrap.sh` instala Codex y Herdr, registra las dos integraciones y añade `python3` y `ncurses-term` a los paquetes base; el repositorio rastrea `config/herdr/config.toml`, este documento y las pruebas; `.gitignore` excluye credenciales y estado de sesión de Herdr; el escaneo de secretos del README ya no informa «limpio» ante errores ni ignora archivos nuevos.
- Este documento: estado actualizado, migración sin `kill-session` a ciegas, matices de `clipboard` y `SSH_CONNECTION`, topología con tmux en ambos extremos y `NO_TMUX`.

## Entorno de origen

| Componente | Valor observado |
|---|---|
| Terminal exterior | Windows Terminal |
| Sistema | Ubuntu dentro de WSL |
| Shell interactivo | zsh |
| Herdr | 0.9.5 |
| Binario de Herdr | `~/.local/bin/herdr` |
| tmux | 3.4 |
| Configuración de Herdr | `~/.config/herdr/config.toml` |
| Configuración de tmux | `~/.tmux.conf` |
| Inicio del shell | `~/.zshrc` |
| Integración de Claude | Instalada y actualizada, v11 |
| Integración de Codex | Instalada y actualizada, v10 |
| Pruebas reproducibles | `~/herdr-tmux-audit/run_checks.py` |
| Auditoría independiente | `~/herdr-tmux-audit/codex-audit-2026-10-24.md` (Codex gpt-6-astra, esfuerzo máximo; solo en este equipo, no se publica en dotfiles) |
| Copia versionada | `~/dotfiles`: `shell/zshrc`, `shell/tmux.conf`, `config/herdr/config.toml`, `docs/herdr-tmux-config.md`, `tools/herdr-tmux-audit/` |

En el servidor de destino hay que comprobar las versiones y el terminal utilizado antes de trasladar estos ajustes. Herdr y tmux pueden tener otras opciones o bindings en versiones distintas.

## Estructura de las sesiones

En el equipo de origen:

```text
Windows Terminal
└── Ubuntu en WSL
    └── tmux                         Ctrl+b
        └── Herdr                    Ctrl+a
            ├── Workspace proyecto A
            │   ├── Pestaña 1 → zsh → Claude Code
            │   └── Pestaña 2 → zsh → shell o proceso del proyecto
            └── Workspace proyecto B
                └── Pestaña 1 → zsh → Codex
```

Una adaptación por SSH puede mantener el mismo orden:

```text
Terminal local → SSH → tmux del servidor → Herdr → shell → agente
```

El problema original era que el inicio automático de zsh producía esta estructura:

```text
tmux → Herdr → otro tmux → agente
```

Herdr veía el cliente de tmux en sus paneles y no detectaba los agentes detrás. La comprobación de `HERDR_ENV` en el shell evita ese segundo tmux. Herdr documenta esta limitación y la condición que permite evitarla en su [guía de detección de agentes](https://herdr.dev/docs/agents/#detection-manifests).

## Configuración activa de Herdr

Archivo: `~/.config/herdr/config.toml`.

```toml
onboarding = false

[ui.toast]
delivery = "herdr"

[ui]
status_indicators = "symbols"
mouse_capture = true
copy_on_select = true
mouse_scroll_lines = 3
prompt_new_tab_name = false

[keys]
prefix = "ctrl+a"
focus_pane_left = ["prefix+h", "prefix+left"]
focus_pane_down = ["prefix+j", "prefix+down"]
focus_pane_up = ["prefix+k", "prefix+up"]
focus_pane_right = ["prefix+l", "prefix+right"]
split_vertical = ["prefix+v", "prefix+percent"]
split_horizontal = ["prefix+minus", "prefix+double_quote"]
```

El prefijo distinto permite controlar Herdr sin hacer `Ctrl+b` dos veces. Las flechas y los símbolos `%` y `"` añaden los movimientos y divisiones habituales de tmux, conservando los bindings originales de Herdr (`h/j/k/l`, `v` y `-`).

`mouse_capture` permite hacer clic en la interfaz y entregar la rueda a Herdr. `copy_on_select` copia la selección al soltar el mouse. `prompt_new_tab_name = false` crea pestañas sin pedir un nombre, como el flujo habitual de tmux. `mouse_scroll_lines = 3` coincide con el valor predeterminado de Herdr.

`delivery = "herdr"` muestra los avisos dentro de la interfaz de Herdr, por ejemplo «● claude finished» cuando termina un agente de otro workspace, y funciona igual por SSH. `delivery = "system"` ejecuta `notify-send` desde el cliente; en este WSL no está instalado ni hay servicio de notificaciones en D-Bus, y Herdr lo omite sin registrar nada ([implementación](https://github.com/herdrdev/herdr/blob/v0.9.5/src/platform/linux.rs#L974-L1004)). `status_indicators` es una preferencia de presentación.

## Configuración activa de tmux

Archivo: `~/.tmux.conf`.

```tmux
##### Terminal & colors
# tmux-256color needs a terminfo entry (ncurses-term on Debian/Ubuntu); fall back when absent
if-shell 'infocmp tmux-256color >/dev/null 2>&1' \
  'set -g default-terminal "tmux-256color"' \
  'set -g default-terminal "screen-256color"'
set -as terminal-overrides ',xterm-256color:Tc'   # truecolor

##### Basics
set -g history-limit 100000
set -g escape-time 0
set -g focus-events on
setw -g mode-keys vi

##### Prefix: Ctrl+b for tmux (Herdr uses Ctrl+a inside); Ctrl+b Ctrl+b sends a literal Ctrl+b
set -g prefix C-b
set -g prefix2 None
bind C-b send-prefix

##### Clipboard: allow Herdr and other pane apps to copy to the system clipboard
set -s set-clipboard on

##### Status (minimal)
set -g status on
set -g status-interval 5
set -g status-left "[#S] "
setw -g automatic-rename on
setw -g automatic-rename-format "#{window_index}:#{pane_current_command}"

##### Mouse: forward events to Herdr and other mouse-aware apps
set -g mouse on
bind -n WheelUpPane if-shell -F -t = '#{||:#{pane_in_mode},#{mouse_any_flag}}' 'send-keys -M' 'copy-mode -e'
bind -n WheelDownPane send-keys -M
bind -T copy-mode-vi WheelUpPane   send-keys -X -N 3 scroll-up
bind -T copy-mode-vi WheelDownPane send-keys -X -N 3 scroll-down

##### Optional: quick toggle (Ctrl-b m) between tmux mouse ON/OFF
bind m if -F '#{mouse}' \
  'set -g mouse off \; display "tmux mouse: OFF (terminal scroll)"' \
  'set -g mouse on  \; display "tmux mouse: ON (pane scroll)"'
```

El prefijo `Ctrl+b` es el predeterminado de tmux y está activo, aunque el archivo no lo declara. `prefix2` está en `None`. `Ctrl+b` → `Ctrl+b` envía un `Ctrl+b` a la aplicación del panel (`send-prefix`, binding predeterminado). Si el servidor tiene otro prefijo y se quiere reproducir exactamente esta distribución, el agente deberá resolver ese cambio con el flujo existente.

`default-terminal` se fija con `if-shell`: usa `tmux-256color` cuando existe su entrada terminfo (paquete `ncurses-term` en Debian/Ubuntu) y, si no, `screen-256color`. Así el mismo archivo sirve en servidores mínimos sin que las aplicaciones de los paneles fallen con «unknown terminal». La misma entrada hace falta al conectar por SSH desde dentro de un tmux local, porque la conexión llega con `TERM=tmux-256color`: instalar `ncurses-term` en el servidor o conectar con `TERM=screen-256color ssh ...`.

### Por qué cambiaron los bindings de la rueda

Antes, la rueda hacia arriba siempre activaba el modo de copia de tmux. Eso capturaba el evento antes de que llegara a Herdr.

El binding actual comprueba si el panel ya está en modo de copia o si la aplicación solicita eventos del mouse. En esos casos entrega el evento con `send-keys -M`. Si es un shell normal que no usa mouse, activa el historial de tmux.

La rueda hacia abajo también se entrega con `send-keys -M`. Los bindings de `copy-mode-vi` desplazan 3 líneas por paso dentro del historial de tmux (`-N 3`), igual que `mouse_scroll_lines` de Herdr; el valor predeterminado de tmux es 5.

El resultado esperado es:

- Sobre Herdr, la rueda llega a Herdr sin activar el modo de copia de tmux. En un panel de shell, Herdr desplaza su historial 3 líneas por paso; si la aplicación del panel pide eventos del mouse (Claude Code, Codex, `lazygit`), Herdr le entrega la rueda y es ella quien decide cómo desplazarse.
- Sobre un shell normal de tmux, el primer paso activa el historial y los siguientes desplazan 3 líneas; al bajar hasta el final se sale del modo de copia.
- `Ctrl+b` → `m` sigue alternando el mouse de tmux; para manejar Herdr con mouse debe quedar activado.

### Por qué se activó el portapapeles

Herdr 0.9.5 copia con OSC 52 cuando detecta WSL, `SSH_CONNECTION`, `SSH_TTY` o `VSCODE_IPC_HOOK_CLI` en el entorno del cliente `herdr`; en otro caso intenta primero `wl-copy` o `xclip` ([implementación](https://github.com/herdrdev/herdr/blob/v0.9.5/src/selection.rs#L337-L376)). OSC 52 es una secuencia de terminal que solicita escribir texto en el portapapeles del cliente.

tmux estaba configurado con `set-clipboard external`, que impide que las aplicaciones internas establezcan ese portapapeles. `set-clipboard on` permite procesar esas solicitudes. El terminal exterior también debe admitirlas. Si hay varios tmux anidados a través de SSH, hay que revisar cada capa. [Documentación del portapapeles de tmux](https://github.com/tmux/tmux/wiki/Clipboard).

Herdr también reenvía el OSC 52 que emiten las aplicaciones de sus paneles (Claude Code, Codex, editores), de modo que esa copia llega igualmente al terminal exterior.

La selección de Herdr copia automáticamente al soltar el botón. Para pegar en Windows Terminal se utiliza `Ctrl+Shift+V`; en otras aplicaciones de Windows, `Ctrl+V`.

## Inicio automático de zsh

Este es el bloque activo de `~/.zshrc`. El resto del archivo contiene la configuración habitual del usuario y no forma parte de esta adaptación.

```zsh
# --- Auto-start tmux: nueva sesión numérica por pestaña (sin awk) ---
if [[ $- == *i* ]] && [[ -t 1 ]] && [[ -z "$TMUX" ]] && [[ -z "$NO_TMUX" ]] && [[ "${HERDR_ENV:-}" != 1 ]] && command -v tmux >/dev/null 2>&1; then
  # Lista de sesiones numéricas existentes (puede estar vacía)
  sessions="$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^[0-9]+$' | sort -n || true)"

  i=0
  # Busca el menor número libre
  while echo "$sessions" | grep -qx "$i"; do
    i=$((i+1))
  done

  # Crea y entra en esa sesión (sin -d y sin detach de otras).
  # Si otro shell tomó el mismo número a la vez ("duplicate session"), prueba el siguiente;
  # cualquier otro fallo de tmux se muestra y termina el bucle.
  until tmux new -s "$i"; do
    tmux has-session -t "=$i" 2>/dev/null || break
    i=$((i+1))
  done
fi
# --- /Auto-start tmux ---
```

La condición nueva es:

```zsh
[[ "${HERDR_ENV:-}" != 1 ]]
```

Herdr establece `HERDR_ENV=1` en los procesos de sus paneles. La condición conserva el inicio automático de tmux fuera de Herdr y lo evita dentro. Se comprobó en ambos sentidos: sin `HERDR_ENV`, el mismo `.zshrc` crea la sesión de tmux `0`; con `HERDR_ENV=1`, no crea ninguna.

El bucle `until tmux new -s "$i"` se añadió el 24 de octubre: cuando varios shells arrancan a la vez (Windows Terminal restaurando pestañas, varias conexiones SSH), dos calculaban el mismo número libre y el segundo fallaba con «duplicate session» y quedaba fuera de tmux. Ahora, si la sesión ya existe, prueba el número siguiente; cualquier otro fallo de `tmux new` sale del bucle. Se verificó con tres shells simultáneos: sesiones `0`, `1` y `2`, los tres dentro de tmux, y salir o desconectarse vuelve al shell sin repetir el bucle.

`NO_TMUX` con cualquier valor no vacío (también `0`) desactiva el inicio automático: `NO_TMUX=1 zsh`. La condición exige además que la salida sea un terminal (`[[ -t 1 ]]`), así `zsh -ic 'comando'` sin TTY ejecuta el comando sin intentar abrir tmux. Un terminal integrado como el de VS Code sí cumple la condición y abre su sesión numerada; si no se desea, exportar `NO_TMUX=1` en ese terminal.

En otro servidor puede existir una sesión fija, un gestor de sesiones o una lógica de inicio diferente. Hay que incorporar la condición a esa lógica, sin copiar obligatoriamente el sistema de sesiones numéricas de este equipo.

El cambio se aplica a los shells nuevos. No extrae los procesos que ya están dentro de tmux ni cambia la estructura de los paneles antiguos.

## Atajos de uso diario

En todos los ejemplos, se pulsa `Ctrl+a`, se suelta y después se pulsa la segunda tecla. `Shift+d` significa una `D` mayúscula.

| Acción de Herdr | Atajo |
|---|---|
| Nueva pestaña | `Ctrl+a` → `c` |
| Pestaña siguiente | `Ctrl+a` → `n` |
| Pestaña anterior | `Ctrl+a` → `p` |
| Ir a una pestaña por número | `Ctrl+a` → `1` a `9` |
| Mover el foco entre paneles | `Ctrl+a` → flecha |
| Mover el foco con teclas vi | `Ctrl+a` → `h`, `j`, `k`, `l` |
| Dividir izquierda y derecha | `Ctrl+a` → `%` o `v` |
| Dividir arriba y abajo | `Ctrl+a` → `"` o `-` |
| Ampliar o restaurar el panel | `Ctrl+a` → `z` |
| Entrar en modo de redimensionado | `Ctrl+a` → `r` |
| Navegar por workspaces | `Ctrl+a` → `w` |
| Buscar un agente o terminal | `Ctrl+a` → `g` |
| Crear un workspace | `Ctrl+a` → `Shift+n` |
| Renombrar un workspace | `Ctrl+a` → `Shift+w` |
| Mostrar u ocultar la barra lateral | `Ctrl+a` → `b` |
| Entrar en modo de copia | `Ctrl+a` → `[` |
| Recargar configuración | `Ctrl+a` → `Shift+r` |
| Mostrar la ayuda y bindings activos | `Ctrl+a` → `?` |
| Enviar `Ctrl+a` a la aplicación (inicio de línea) | `Ctrl+a` → `Ctrl+a` |
| Cerrar el panel actual, sin confirmación | `Ctrl+a` → `x` |
| Cerrar la pestaña actual, sin confirmación | `Ctrl+a` → `Shift+x` |
| Cerrar el workspace actual, con confirmación | `Ctrl+a` → `Shift+d` |
| Salir de la interfaz manteniendo la sesión | `Ctrl+a` → `q` |

`x` y `Shift+x` cierran de inmediato aunque el panel tenga un proceso en marcha: un agente que esté trabajando ahí se termina. Solo el cierre de workspace pide confirmación (`Enter` confirma, `Esc` cancela). Después de cancelar con `Esc`, Herdr queda en modo de navegación (`NAVIGATE` en la barra inferior): hay que pulsar `Esc` otra vez antes de escribir.

En modo de copia se mueve con `h/j/k/l`, `w/b/e` y `{ }`; se busca hacia abajo con `/` y hacia arriba con `?`, repitiendo con `n/N`; se inicia la selección con `v` o Espacio; `y` o Enter copian y salen del modo; `q` sale (`Esc` primero borra la búsqueda). La barra inferior muestra esta leyenda. [Referencia de teclado de Herdr](https://herdr.dev/docs/keyboard/#copy-mode).

`Ctrl+b` conserva el control de tmux exterior. Por ejemplo, `Ctrl+b` → `c` crea una ventana de tmux; `Ctrl+a` → `c` crea una pestaña de Herdr.

Salir con `Ctrl+a` → `q` deja los agentes funcionando. Ejecutar `herdr` vuelve a conectar con la sesión, con los mismos paneles y procesos.

Para detener el servidor de Herdr y sus paneles, el comando es `herdr server stop`. Es una operación de apagado, no un paso de recarga de configuración.

## Detección de Claude Code y Codex

Para un agente nuevo:

1. Crear un panel o pestaña de Herdr.
2. Entrar al directorio del proyecto desde ese shell.
3. Ejecutar `claude` o `codex` directamente.
4. Consultar `herdr agent list` para verificar su detección.

En un shell recién abierto por Herdr:

```sh
printf 'HERDR_ENV=%s TMUX=%s\n' "${HERDR_ENV:-}" "${TMUX:-}"
```

En esta estructura, el resultado esperado es:

```text
HERDR_ENV=1 TMUX=
```

Que haya agentes ejecutándose en otros tmux o terminales no hace que aparezcan automáticamente en Herdr. Las conversaciones existentes se deben reanudar directamente en Herdr cuando corresponda; modificar el shell no migra procesos.

Comandos para revisar las integraciones:

```sh
herdr integration status
```

Si faltan en el servidor de destino, los comandos de instalación son:

```sh
herdr integration install claude
herdr integration install codex
```

Las integraciones se instalan donde se ejecutan los agentes. En el equipo de origen, ambas están instaladas y actualizadas. En la prueba aislada, `codex` ejecutado directamente en un panel de Herdr apareció al instante como agente `codex` (estado `idle`) y desapareció al salir. Codex informa su identidad de sesión, que Herdr usa para reanudarlo tras un reinicio, a partir de la primera petición; la prueba no envió ninguna.

### Estado en este equipo (24 de octubre de 2026)

Ya no queda ningún tmux dentro de Herdr: el único servidor tmux tiene la sesión `0`, que ejecuta Herdr, y `herdr agent list` muestra todos los agentes activos (Claude y Codex) en paneles de Herdr. La migración descrita el 20 de octubre (Codex dentro de la sesión `4`) está hecha. Si vuelve a aparecer un panel cuyo proceso visible sea `tmux`: identificar primero qué contiene esa sesión (`tmux list-windows -t N` y `tmux list-panes -t N -F '#{pane_pid} #{pane_current_command}'`), salir del agente que esté dentro y, solo si la sesión queda vacía o únicamente con ese shell, `tmux kill-session -t N`; si tiene otras ventanas, basta con `tmux detach-client -s N` y cerrar el panel de Herdr. Después, reanudar el agente en una pestaña nueva de Herdr (`claude --resume` o `codex resume`).

## Aplicación y recarga

Después de integrar los cambios de tmux:

```sh
tmux source-file ~/.tmux.conf
```

`set -as terminal-overrides` añade una entrada repetida en cada recarga; es inofensivo. Para un cambio pequeño también se puede aplicar solo el binding modificado con `tmux bind ...`.

Después de editar Herdr:

```sh
herdr server reload-config
```

Esta recarga aplica `config.toml` en el servidor. Los atajos, incluido el prefijo, `mouse_scroll_lines` y las notificaciones pasan al instante a todos los clientes conectados; se comprobó con dos clientes. Si se cambia el prefijo, el nuevo queda activo en todos los clientes después de esta recarga.

`Ctrl+a` → `Shift+r` hace lo mismo desde un cliente y además recarga los ajustes locales de ese cliente: `mouse_capture`, sonido, `host_cursor` y `redraw_on_focus_gained` ([implementación](https://github.com/herdrdev/herdr/blob/v0.9.5/src/client/config_reload.rs#L93-L130)). Solo hace falta en cada cliente cuando cambian esos ajustes. Con sesiones con nombre, usar la sesión correspondiente, por ejemplo `herdr --session NOMBRE server reload-config`.

Ninguna de las dos recargas reinicia los paneles: las pruebas compararon los PID de los shells antes y después.

Los cambios de `.zshrc` se validan con:

```sh
zsh -n ~/.zshrc
```

Luego se abre una pestaña nueva de Herdr. Volver a ejecutar `herdr` se conecta a paneles existentes y no los convierte en shells nuevos.

## Verificaciones realizadas

Prueba reproducible:

```sh
python3 ~/herdr-tmux-audit/run_checks.py
```

Usa tmux y Herdr reales en sockets propios (`TMUX_TMPDIR`, `XDG_CONFIG_HOME` y `HERDR_CONFIG_PATH` dentro de un directorio temporal), el `~/.tmux.conf` real en solo lectura y una copia idéntica de la configuración de Herdr, que restaura después de cada cambio. Un segundo tmux privado hace de terminal exterior: recibe teclado y eventos SGR del mouse y registra la salida para decodificar OSC 52. No toca los servidores en uso; al terminar comprueba que no quedan procesos de la prueba, que los paneles reales no cambiaron y que el historial real de zsh no recibió comandos. Los resultados quedan en `<raíz>/run/results.json`. Variables: `HERDR_AUDIT_ROOT` (raíz; corta, por el límite de longitud de los sockets), `AUDIT_SKIP_CODEX=1` (no abre Codex) y `HERDR_AUDIT_PROMPT` (texto que identifica el prompt de zsh). `--only 17,19` repite solo esas comprobaciones (la 01 siempre arranca la pila). La raíz debe estar vacía o haber sido creada por la propia prueba; si queda un servidor de una ejecución anterior, se niega a continuar hasta ejecutar `python3 ~/herdr-tmux-audit/auditlib.py teardown`, y nunca detiene un servidor de Herdr cuyo socket esté fuera de esa raíz. Termina con código distinto de cero si falla alguna comprobación o la limpieza. Solo Linux.

Resultado de la última ejecución, 24 de octubre de 2026, 20 de 20:

1. Aislamiento: los sockets de Herdr y tmux quedan dentro de la raíz de la prueba y el cliente sintético anuncia `clipboard`.
2. Un shell nuevo de Herdr tiene `HERDR_ENV=1`, no tiene `TMUX`, solo ejecuta `zsh` e imprime `HERDR_ENV=1 TMUX=`.
3. Sin `HERDR_ENV`, el `.zshrc` crea la sesión de tmux `0`; con `HERDR_ENV=1` o con `NO_TMUX=1`, ninguna; `zsh -ic` sin TTY ejecuta el comando sin intentar abrir tmux. Además (3b), tres shells que arrancan a la vez obtienen las sesiones `0`, `1` y `2` sin «duplicate session».
4. Cinco pasos de rueda sobre Herdr desplazan exactamente 15 líneas, sin activar el modo de copia de tmux; bajar vuelve a 0.
5. `mouse_scroll_lines` se aplica: con 7 da 35 líneas y, restaurado, 15.
6. Al arrastrar, el OSC 52 que llega al terminal decodifica exactamente el texto seleccionado y coincide con el buffer de tmux.
7. Modo de copia (`Ctrl+a` → `[`, `?texto`, `v`, `e`, `y`): OSC 52 exacto; `y` sale y vuelve al final.
8. El OSC 52 emitido por una aplicación dentro de un panel llega al terminal.
9. `Ctrl+a` → `c` crea una pestaña sin diálogo; `p`, `n`, `1` y `2` cambian de pestaña.
10. `%` y `v` dividen lado a lado y `"` y `-` arriba y abajo, comprobado por la geometría de los paneles; las flechas y `h/j/k/l` mueven el foco; un prefijo equivale a una acción.
11. `Ctrl+a` → `Ctrl+a` envía un `Ctrl+a` literal.
12. `herdr server reload-config` cambia el prefijo y `mouse_scroll_lines` sin `Shift+r`; los PID de los shells no cambian.
13. Con dos clientes conectados, una recarga del servidor cambia el prefijo en ambos.
14. `Ctrl+a` → `q` mantiene el servidor y los procesos; `herdr` vuelve a los mismos paneles y PID.
15. `x` cierra un panel ocupado sin preguntar; `Shift+x` cierra la pestaña y sus shells; `Shift+d` pregunta, `Esc` cancela y deja el modo `NAVIGATE`, y `Enter` cierra el workspace y termina sus shells.
16. `Ctrl+b` → `c` funciona con Herdr enfocado; en un shell normal, el primer paso de rueda activa el historial y cinco pasos desplazan 12 líneas; al bajar se sale; `Ctrl+b` → `Ctrl+b` es `send-prefix`.
17. Codex ejecutado en un panel de Herdr se detecta al instante y desaparece al salir (`Esc` cierra un diálogo de inicio como «update available», luego `Ctrl+C` dos veces y, si hiciera falta, `/exit`).
18. La ayuda (`Ctrl+a` → `?`) muestra `ctrl+a` como prefijo.
19. Un agente que termina en otro workspace muestra «● claude finished» con `delivery = "herdr"`; con `"system"` no aparece ningún aviso dentro de Herdr (la prueba no puede ver avisos de escritorio).

También se comprobó que los bloques de configuración de este documento coinciden byte a byte con los archivos activos, que el tmux en uso tiene los mismos atajos y opciones que uno nuevo cargado desde `~/.tmux.conf` (salvo la entrada repetida de `terminal-overrides`) y que `herdr config check` responde `ok`.

Quedan por comprobar desde el cliente real: pegar en una aplicación de Windows lo copiado en Herdr (solo falta confirmar que Windows Terminal acepta el OSC 52), la sensación de la rueda o del touchpad en Windows Terminal, las teclas `[`, `%` y `"` con la distribución de teclado del usuario y la cadena SSH completa.

### Comprobación en el servidor de destino

Revisar versiones y estado:

```sh
herdr --version
tmux -V
herdr status server
herdr config check
herdr integration status
tmux show-options -g prefix
tmux show-options -g mouse
tmux show-options -s set-clipboard
tmux list-keys -T root WheelUpPane
tmux list-keys -T root WheelDownPane
tmux list-keys -T copy-mode-vi WheelUpPane
tmux list-clients -F '#{client_termname} #{client_termfeatures}'
```

La última línea muestra, por cliente, las capacidades que tmux detectó; `clipboard` aparece para terminales `xterm*` (`terminal-features`). Si no aparece, comprobar la capacidad `Ms` del terminfo (`infocmp -x "$TERM" | grep -o 'Ms=[^,]*'`): tmux reenvía OSC 52 cuando `set-clipboard` está en `on` y `Ms` existe por cualquiera de las dos vías. La prueba definitiva sigue siendo pegar en el terminal local.

Comprobar también los ajustes efectivos de la sesión usada, porque puede tener opciones propias que sustituyan las globales:

```sh
tmux show-options -A mouse
tmux show-options -A prefix
```

En el shell desde el que se lanza `herdr` en el servidor:

```sh
printf 'SSH_CONNECTION=%s SSH_TTY=%s\n' "${SSH_CONNECTION:-}" "${SSH_TTY:-}"
```

Alguna de las dos debe tener valor: Herdr prefiere OSC 52 cuando ve `SSH_CONNECTION` o `SSH_TTY` (también en WSL o VS Code). Sin ellas, por ejemplo en un tmux iniciado por systemd o en un shell creado antes de conectar por SSH, intenta `wl-copy` o `xclip` antes que OSC 52 y la copia puede quedarse en el servidor.

En un panel de shell nuevo de Herdr, generar texto de prueba:

```sh
seq 1 300
```

Comprobar rueda en ambas direcciones, selección, pegado en una aplicación local, pestañas, divisiones y foco. Ejecutar cada comando en el shell de prueba, no dentro del prompt de un agente que esté trabajando.

Para investigar agentes:

```sh
herdr pane list
herdr agent list
```

Copiar un ID real de `herdr pane list` y usarlo en `herdr pane process-info --pane ID_REAL`. Si el proceso visible es `tmux`, todavía hay un tmux dentro de ese panel.

## Adaptación al servidor y mantenimiento

El agente receptor debe comprobar el shell, las versiones, el tipo de terminal y la cadena de conexión. Si existe tmux tanto en el cliente local como en el servidor remoto, ambas capas pueden intervenir en el teclado, el mouse y el portapapeles.

Topología con tmux en los dos extremos: `Ctrl+b` lo captura el tmux más exterior, es decir, el local. Para que `Ctrl+b` controle el tmux del servidor hay que conectar desde una pestaña sin tmux local (`NO_TMUX=1 zsh` y después `ssh`), o pulsar `Ctrl+b` `Ctrl+b` (el primero lo consume el local y el segundo llega al remoto), o dar al tmux local otro prefijo. Lo mismo ocurre con `Ctrl+a` si hay Herdr en ambos lados. Para el mouse y el portapapeles, cada capa de tmux necesita `mouse on` y `set-clipboard on`; con `set-clipboard on`, cualquier programa que escriba en el terminal puede fijar el portapapeles y crear buffers de tmux, un requisito de esta vía que conviene conocer ([tmux: clipboard, security concerns](https://github.com/tmux/tmux/wiki/Clipboard#security-concerns)).

Si por SSH las flechas o las combinaciones con Alt llegan partidas, cambiar `set -g escape-time 0` por `set -s escape-time 50` en el servidor y volver a probar. Conviene aplicar en este orden: paquetes y binarios → archivos de configuración → integraciones de Herdr → `herdr config check` → recargas (`tmux source-file`, `herdr server reload-config`) → shells nuevos.

Los ajustes de colores y `default-terminal` deben corresponder al terminal y a la base terminfo del servidor. Los ajustes visuales y de notificaciones se pueden adaptar al entorno; los cambios esenciales para este flujo son los prefijos separados, el reenvío de la rueda, el portapapeles y la condición `HERDR_ENV`.

En este equipo, `~/dotfiles` funciona por copia: `install.sh` copia el repositorio a `$HOME`, con copia de seguridad previa, y `save.sh` hace lo contrario. Desde el 24 de octubre de 2026, `shell/zshrc`, `shell/tmux.conf`, `config/herdr/config.toml`, `docs/herdr-tmux-config.md` (este documento) y `tools/herdr-tmux-audit/` coinciden con los archivos activos; `git -C ~/dotfiles log -3` muestra los commits, que no se publican sin confirmación del usuario. El repositorio rastrea los hooks propios de Claude Code (`claude/hooks/`) y `claude/settings.json`, pero `save.sh` quita la entrada del hook de Herdr porque `herdr integration install claude` la vuelve a escribir en cada equipo con su ruta absoluta y no reconoce una entrada reescrita: después de `install.sh` hay que ejecutar `herdr integration install claude` y `herdr integration install codex`, como indica su README (`bootstrap.sh` ya lo hace). Al cambiar estos archivos, ejecutar `save.sh` o copiar el archivo concreto antes de desplegar.

Si Herdr no está en el servidor: `curl -fsSL https://herdr.dev/install.sh | sh` lo instala en `~/.local/bin` sin sudo ni preguntas (necesita `curl` y `awk`); también existe `brew install herdr`. `~/dotfiles/bootstrap.sh` incluye ese paso, la instalación de Codex y las dos integraciones, y `install.sh` restaura `~/.config/herdr/config.toml`; si ya hay un servidor de Herdr en marcha, después hay que ejecutar `herdr server reload-config`. El instalador descarga la última versión publicada; esta guía se verificó con 0.9.5, y para fijar esa versión se descarga su binario desde las releases de GitHub.

Para trasladar la configuración, usar los ajustes de texto e instalar las integraciones en destino. Los sockets y los IDs de panes o sesiones pertenecen al proceso y equipo que los crearon. Las pruebas de `~/herdr-tmux-audit/` se pueden copiar al servidor; suponen zsh, prefijo `Ctrl+a`, Python 3 y Codex instalado (o `AUDIT_SKIP_CODEX=1`).

## Instrucción para el agente que hará la adaptación

```text
Lee este documento y adapta mi servidor para usar tmux como entorno exterior
y Herdr para organizar los agentes, conservando mi configuración existente.

Quiero Ctrl+b para tmux y Ctrl+a para Herdr, sin doble prefijo. Quiero moverme
con prefijo y flechas, dividir con % y comillas dobles, cambiar pestañas con
n y p, usar la rueda sobre el panel correcto y copiar texto al portapapeles
del terminal desde el que me conecto.

Inspecciona versiones, shell, archivos activos, dotfiles y cadena SSH antes
de editar. Integra los ajustes necesarios y conserva las personalizaciones
que no estén relacionadas. Adapta colores al entorno real y usa
delivery = "herdr" salvo que el servidor tenga un servicio de notificaciones.

Evita que el inicio automático del shell cree otro tmux dentro de Herdr.
Ejecuta los agentes directamente en paneles de Herdr, migra los que sigan
dentro de otro tmux y revisa sus integraciones. Mantén las sesiones existentes
durante la adaptación.

Comprueba que el shell que lanza herdr tenga SSH_CONNECTION y que
tmux list-clients muestre clipboard en cada capa de tmux.

Prueba en una sesión aislada el teclado, el mouse, el scroll, la copia y la
recarga; puedes adaptar ~/herdr-tmux-audit/run_checks.py. Verifica que tmux
siga funcionando fuera de Herdr. La prueba del portapapeles debe cubrir
también mi terminal cliente y cualquier tmux local.

Recarga tmux y aplica Herdr con herdr server reload-config; Ctrl+a Shift+r
solo hace falta en cada cliente si cambian sus ajustes locales.
Entrega los archivos modificados, los atajos finales, los resultados de las
pruebas y cualquier paso que dependa de mi terminal o de mis sesiones actuales.
```
