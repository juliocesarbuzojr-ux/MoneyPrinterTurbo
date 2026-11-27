# Contexto completo de la sesión anterior (léelo antes de hacer nada)

Este documento resume TODO lo que se habló y se hizo en la sesión en la nube donde se creó la
versión 1 de este video. La sesión nueva corre en la PC del usuario (Windows, **RTX 3070**,
**Blender 5.3**) y debe continuar con la **versión 2** (ver `PLAN_V2.md`).

- Repo: `juliocesarbuzojr-ux/MoneyPrinterTurbo`, rama `claude/rotary-engine-pixel-animation-20586i`,
  carpeta `pixel_art_videos/motor_rotativo/`.
- Carpeta del usuario donde va todo: `C:\Users\USUARIO\Desktop\pixel art videos`
  (efectos de sonido en `pixel art videos\sfx` si ya existen; si no, usar los de `sfx/` de esta carpeta).
- El usuario habla español; todos los textos del video van en español.

---

## 1. Lo que pidió el usuario al principio (sus reglas, siguen vigentes salvo lo que cambió después)

**Tema:** cómo funciona un motor rotativo. Se ve el carro pasando por un puente, zoom a la cubierta del
motor para llegar al motor y ahí empieza toda la explicación.

Hazme un video explicativo en 3D con Blender, estilo pixel art, siguiendo TODO esto:

### 1.1 Formato
- Vertical 9:16 para reels: **1080×1920**. **24 cuadros por segundo.** Duración aproximada: 30–40 segundos.
- ~~Fondo negro puro~~ → **cambió en la v2** (paisaje de atardecer en el puente; gris muy oscuro dentro del motor).
- Textos en **español**.

### 1.2 Cómo se hace el render
- Script de Python para Blender que arme todo (modelos, materiales, luces, cámara y animación),
  guardado en `C:\Users\USUARIO\Desktop\pixel art videos`.
- Un `.bat` que corra Blender 5.3 en segundo plano (`blender.exe --background --factory-startup --python ...`)
  y se ejecute en la PC (doble clic). La tarjeta de video renderiza todo en 2–4 minutos.
- Al terminar, el script mete todos los cuadros en un `.zip`. Luego se aplica el estilo final, textos y
  sonido, y se entrega el **MP4** en la misma carpeta, junto con el **`.blend`** y los **scripts**.

### 1.3 Estilo visual (lo más importante)
- Render en Eevee ~~a 270×480~~ (**v2: 540×960**) sin suavizado (`filter_size = 0`) y con fondo transparente.
  Después se agranda sin difuminar (nearest neighbor) para que cada pixel quede como un cuadrito.
- Materiales **realistas** (Principled BSDF), no toon: metal cromado con reflejos (metallic 1, roughness bajo)
  en tubos y escape; pintura roja/naranja para tapas; bloque gris azulado oscuro; piezas de goma negras;
  grano casi nulo (bump 0.03–0.06).
- **Ambiente de estudio** (mundo con degradado: suelo oscuro, horizonte gris y una banda de luz brillante)
  para que el metal tenga algo que reflejar.
- Luz principal cálida desde el lado de la cámara y luz de contorno azulada desde atrás.
- **Contorno negro** en cada pieza (Solidify con normales invertidas). El contorno **no debe hacer sombra**:
  material con *backface culling* de sombra y la mezcla "Is Shadow Ray → Transparent".
- **Tramado (dithering) bien hecho:** paleta fija de ~40 colores para todo el video (k-means con pixeles de
  varios cuadros, más negro y blanco); cada pixel toma su color más cercano; solo se trama con Bayer 4×4
  cuando el pixel queda **entre dos colores parecidos**; zonas planas limpias. **NO** reducir cada canal RGB
  por separado (llena todo de puntitos azules, verdes y grises).
- Partículas brillantes (fuego naranja, aire cian, aceite amarillo) con un pequeño resplandor.
- Piezas en corte: cara del corte con **rayas diagonales** rojo oscuro/naranja; interior caliente naranja liso
  y frío cian oscuro liso (sin remolinos).

### 1.4 Nivel de detalle
Nada de cajas simples: tornillos, bridas, abrazaderas en tubos, aletas (alternador), poleas con agujeros,
banda, cables y conectores, varilla de aceite con mango amarillo, filtro, nervaduras, tapones y letras en la
tapa. **Formas originales: sin logos ni marcas reales.**

### 1.5 Cómo se presenta cada pieza
1. Primero se ve por fuera, puesta en el motor o en el conjunto. 2. Zoom hacia esa pieza por fuera.
3. Aparece la pieza cerrada de cerca y la cámara sigue acercándose. 4. La **mitad de enfrente se abre y sale
volando** (golpe metálico + whoosh) y la cámara **se mete al interior**. 5. Adentro se explica con partículas y
movimiento. 6. Para la siguiente parte se repite. 7. Al final la cámara sale y se aleja hasta ver todo el
conjunto, y luego viene el cierre.

### 1.6 Textos y etiquetas
- Al inicio de cada escena, **título numerado** ("1. ...", "2. ...") en letra pixel, con su color (naranja,
  amarillo, blanco o cian), letra por letra, con una rayita debajo. Debajo, una frase corta en blanco.
  Franja negra semitransparente detrás.
- **Etiquetas**: caja negra con borde blanco, en mayúsculas, unidas con línea y punto a la pieza; siguen a la
  pieza en pantalla y aparecen **cuando ya se abrió la pieza**.
- Escena de título al inicio (pregunta) y escena de cierre con frase final.
- Letra pixel sin suavizado (DejaVu Sans Mono Bold chica, agrandada con nearest neighbor), legible.

### 1.7 Sonido
- Efectos reales **CC0** de **wyzowl/sfx-kit** (`git clone https://github.com/wyzowl/sfx-kit`; ya están en `sfx/`):
  cambio de escena `whoosh-medium-medium`; antes de un zoom `reverse-whoosh-medium-soft`; zoom `move-zoom-in`,
  al alejarse `move-zoom-out`; al abrir una carcasa `mechanical-latch-heavy` + `cinematic-metal-big` y
  `whoosh-fast-medium` cuando sale volando; al escribir un título `keyboard-letter-soft`; etiquetas
  `appear-poof` + `click-snap-soft`; título inicial `impact-deep-firm`; cierre `boom-hit-medium` + `shimmer-medium-sparkle`.
- Música chiptune 8-bit generada con código: bajo triangular, arpegio de onda cuadrada, bombo y hi-hat de
  ruido, 120 BPM, volumen bajo.
- Generados con código lo que el paquete no trae (motor, escape, chispa, explosión, etc.).
- Todo sincronizado; mezcla con compresión suave, sin saturar.

### 1.8 Antes de entregar
Revisar cuadros de cada escena: textos legibles, tramado limpio, etiquetas apuntando a la pieza correcta.
Entregar el video final con sonido.

---

## 2. Lo que ya se hizo (versión 1, en esta carpeta)

| Archivo | Qué hace |
|---|---|
| `rotativo_comun.py` | Tiempos de cada escena (`F`), geometría real Wankel (epitrocoide, envolvente del rotor R=1, e=0.15), ángulo del eje por cuadro, puntos de la cámara para partículas, caminos de admisión/escape, movimiento del carro |
| `motor_rotativo_blender.py` | Arma todo en Blender: motor (carcasa en corte, rotor, corona interna 24 dientes, piñón fijo 16, excéntrica, bujías, alternador con aletas, poleas con agujeros, banda, filtro, varilla amarilla, plenum con letras "ROTATIVO", tubos cromados en corte), carro deportivo rojo, puente colgante, cámara, luces, contornos con grosor según la distancia; exporta `camara_por_cuadro.json` y el `.blend`; renderiza y hace el `.zip` |
| `render_motor_rotativo.bat` | Corre Blender 5.3 en segundo plano con el script (busca blender.exe en `C:\Program Files\Blender Foundation\`) |
| `postproceso.py` | Paleta fija de 40 colores (k-means + colores fijos), tramado Bayer solo entre colores parecidos, suavizado que respeta bordes, partículas (aire cian, gasolina, fuego, gases, aceite), brillo de la explosión, títulos letra por letra, frases, etiquetas que siguen a la pieza, ×4 nearest y MP4 |
| `audio_motor_rotativo.py` | Efectos CC0 sincronizados, chiptune 120 BPM, motor sintetizado, aspiración, compresión, chispa + explosión, pulsos de escape, engranes; compresor + limitador a −1 dBFS |
| `sfx/` | Los 13 efectos CC0 usados |
| `PLAN_V2.md` | Lo que hay que hacer en la versión 2 |

Escenas de la v1 (24 fps, 948 cuadros = 39.5 s): 0 puente + pregunta → 84 zoom al capot (se abre en 126)
→ 156 "1. MOTOR ROTATIVO" (por fuera) → 252 "2. ROTOR Y CARCASA" (se abre el frente en 292) → 360 "3. ADMISIÓN"
→ 444 "4. COMPRESIÓN" → 528 "5. COMBUSTIÓN" → 612 "6. ESCAPE" → 696 "7. EJE EXCÉNTRICO" (sale volando la cara del
rotor en 736) → 804 la cámara sale → 876 cierre "¡ASÍ FUNCIONA!". En cámara lenta cada tiempo = 270° del eje
= 90° del rotor; una cara del rotor hace los 4 tiempos en una vuelta del rotor (3 vueltas del eje).

Cómo correr la v1 completa:
```
render_motor_rotativo.bat                       (render en la RTX 3070 → render\cuadros, .blend, .json, .zip)
python audio_motor_rotativo.py --out audio.wav
python postproceso.py --render render --audio audio.wav --out motor_rotativo.mp4
```
(Python con numpy, scipy, pillow y ffmpeg en el PATH.)

### Notas técnicas aprendidas
- Con el módulo `bpy` de pip hay que importar `bpy` antes que `bmesh`.
- En Blender 5.x las fcurves se leen con `bpy_extras.anim_utils.action_get_channelbag_for_slot`
  (ya no existe `action.fcurves`). Para propiedades escalares usar `keyframe_insert(..., index=-1)`.
- `ArrayModifier` no tiene `move_to_end`.
- Eevee con 4 muestras se ve casi igual que con 16 (en GPU se puede dejar 16).
- En la nube (sin GPU) Eevee tardaba 5–10 s por cuadro y a veces se caía; por eso el render va en la PC.
- El script admite `--frames 0-100`, `--samples N`, `--engine CYCLES --gpu` y `--reanudar` (no rehace el .json/.blend).

---

## 3. Lo que pidió el usuario después (versión 2) — detalle en `PLAN_V2.md`

1. **Calidad como su video de ejemplo** (un reel de pixel art que explica un turbo; el usuario lo puede
   volver a adjuntar). Lo que se ve en ese ejemplo: pixel más fino (≈540 px de ancho), atardecer con puente
   colgante y ciudad de fondo, títulos grandes blancos/naranjas con contorno negro grueso, cuadros de subtítulos
   que se escriben letra por letra, **flechas chevron animadas** con textura de puntitos dentro de los tubos
   (naranja = humo/gases calientes, azul = aire), medallas numeradas ("1 EL HUMO", "2 LAS RUEDAS"),
   etiquetas con caja y línea, letrero "¡PUM!" en la explosión, HUD con barra de RPM, fondo gris oscuro
   dentro del motor. **No copiar la marca/nombre de ese canal.**
2. **Puente grande de 4 carriles estilo puente de Brooklyn (Nueva York)**, con **mar** de fondo,
   **atardecer**, ciudad a lo lejos y **otros carros pasando**.
3. **Motor de 4 rotores** como el del **Mazda 787B (motor R26B)**, famoso por su sonido. El usuario pensaba
   que era "de 10 cilindros"; se le explicó que en rotativos se cuentan rotores, y que cada rotor da una explosión
   por vuelta del eje (como 2 cilindros), así que 4 rotores suenan como un motor de 8 cilindros a muy altas RPM.
   Sin marcas ni la pintura real del 787B.
4. **Sonido** del motor de 4 rotores a altas RPM generado con código (aullido agudo + "brap"); no usar
   grabaciones reales con derechos.
5. **El carro protagonista ahora es un prototipo de carreras tipo Le Mans** con formas y colores inventados.
   El motor va atrás del piloto: el zoom va a la **cubierta trasera del motor**, que se abre y sale volando.

## 4. Entrega
MP4 final con sonido + `.blend` + scripts en `C:\Users\USUARIO\Desktop\pixel art videos`.
Revisar cuadros de cada escena antes de entregar.
