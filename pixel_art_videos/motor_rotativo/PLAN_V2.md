# Plan versión 2 — "¿Cómo funciona un motor rotativo?"

La versión 1 (esta carpeta) ya funciona: escena de Blender, postproceso pixel art, audio.
La versión 2 mantiene todo el flujo (script de Blender → cuadros → postproceso → MP4) y agrega lo siguiente.
Renderizar en la PC con la RTX 3070 (`render_motor_rotativo.bat`).

## 1. Calidad (como el video de ejemplo que mandó el usuario)
- Render a **540×960** y agrandar **×2** con nearest neighbor (antes 270×480 ×4). Ajustar `RES_X/RES_Y`
  en `rotativo_comun.py`, el grosor del contorno, el periodo de las rayas y los tamaños de letra/partículas.
- Títulos grandes con **contorno negro grueso** (2–3 px) y sombra; cuadros de subtítulo negros con borde.
- **Medallas numeradas** (cuadro naranja con número + texto: "1 ADMISIÓN", "2 COMPRESIÓN"…).
- **Flechas animadas (chevrones)** con textura de puntitos dentro de los tubos y la cámara:
  azules para el aire que entra, naranjas para los gases que salen.
- Letrero **"¡PUM!"** grande en la explosión.
- **Barra de RPM** abajo (HUD tipo videojuego) que sube y baja con el motor.
- Dentro del motor: fondo **gris muy oscuro** con piezas tenues, en vez de negro puro.
- Sin la marca ni el nombre del canal del video de ejemplo.

## 2. Puente y paisaje
- Puente grande de **4 carriles** estilo **puente de Brooklyn (Nueva York)**: torres de piedra con dos arcos
  góticos apuntados, cables principales, red de tirantes diagonales, banquetas, faroles.
- **Atardecer**: cielo degradado naranja → morado, sol bajo, **mar** con reflejos, ciudad con edificios a lo lejos.
- **Tráfico**: otros carros (formas originales) pasando en ambos sentidos, con faros y calaveras encendidos.
- **Carro protagonista: prototipo de carreras tipo Le Mans** (decidido por el usuario), con formas y colores
  inventados, sin logos ni la pintura real de ningún equipo: carrocería baja y ancha, cabina cerrada tipo burbuja,
  aleta trasera, alerón grande, tomas de aire laterales, rines de carreras, números de competencia inventados.
  El motor de 4 rotores va **atrás del piloto** (motor central): el zoom va a la **cubierta trasera del motor**
  (no al capot delantero), que se abre y sale volando igual que en la versión 1.

## 3. Motor de 4 rotores (tipo el del Mazda 787B / R26B, sin marcas ni logos)
- 4 carcasas de rotor en fila con placas intermedias, 4 tubos de admisión cromados, 4 escapes que se juntan,
  **8 bujías** (2 por rotor) con cables, eje excéntrico con **4 excéntricas a 90°**.
- La explicación (admisión, compresión, combustión, escape) sigue en el **primer rotor en corte**.
- **Escena nueva**: la cámara se aleja y se ven los 4 rotores en corte a la vez, cada uno en un tiempo distinto
  ("siempre hay uno explotando: por eso gira tan suave").
- Dato en pantalla: "4 rotores = 8 explosiones por vuelta del eje… por eso suena así".

## 4. Sonido
- Motor de **4 rotores a altas RPM** generado con código: aullido agudo (frecuencia de explosión = 4 × RPM/60)
  más el "brap" en bajas. No usar grabaciones reales con derechos.
- Mantener los efectos CC0 de `wyzowl/sfx-kit` y la música chiptune 120 BPM a volumen bajo.

## 5. Antes de entregar
Revisar cuadros de cada escena (textos legibles, tramado limpio, etiquetas apuntando bien) y entregar
el MP4 final con sonido, el `.blend` y los scripts en `C:\Users\USUARIO\Desktop\pixel art videos`.
