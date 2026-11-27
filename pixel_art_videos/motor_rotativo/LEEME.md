# ¿Cómo funciona un motor rotativo? — animación 3D pixel art

Video vertical 1080×1920, 24 fps, ~39.5 s, fondo negro, textos en español.

## Archivos
| Archivo | Qué es |
|---|---|
| `motor_rotativo.mp4` | Video final con sonido |
| `motor_rotativo.blend` | Escena de Blender 5.3 (carro, puente, motor, cámara y animación) |
| `motor_rotativo_blender.py` | Script que arma TODO en Blender y renderiza los cuadros (270×480, fondo transparente) + `.zip` |
| `render_motor_rotativo.bat` | Doble clic en Windows: corre Blender 5.3 en segundo plano con el script |
| `rotativo_comun.py` | Tiempos de cada escena y geometría real del motor Wankel (epitrocoide, rotor, eje excéntrico) |
| `postproceso.py` | Paleta fija de 40 colores, tramado Bayer selectivo, partículas, títulos, etiquetas, ×4 sin difuminar y MP4 |
| `audio_motor_rotativo.py` | Mezcla: efectos CC0 de `wyzowl/sfx-kit`, música chiptune 120 BPM y sonidos generados (motor, chispa, explosión, escape…) |
| `sfx/` | Los efectos CC0 usados (licencia en `sfx/LICENSE-CC0.txt`) |

## Volver a renderizar en tu PC
1. Pon esta carpeta en `C:\Users\USUARIO\Desktop\pixel art videos\`.
2. Doble clic en `render_motor_rotativo.bat` (busca Blender 5.3 en `C:\Program Files\Blender Foundation\`).
3. Salen los cuadros en `render\cuadros\`, el `.blend`, `render\camara_por_cuadro.json` y `render\cuadros_motor_rotativo.zip`.
4. Postproceso y audio (Python 3 con `numpy`, `scipy`, `pillow` y `ffmpeg`):
   ```
   python audio_motor_rotativo.py --out audio.wav
   python postproceso.py --render render --audio audio.wav --out motor_rotativo.mp4
   ```

## Escenas
0. Puente: el carro cruza — "¿Cómo funciona un motor rotativo?"
1. Zoom al capot, el capot sale volando → **1. MOTOR ROTATIVO** (por fuera, en el vano)
2. Zoom al frente del motor, la mitad de enfrente sale volando → **2. ROTOR Y CARCASA** (en corte)
3. **3. ADMISIÓN** · 4. **COMPRESIÓN** · 5. **COMBUSTIÓN** · 6. **ESCAPE** (una cara del rotor hace los 4 tiempos en una vuelta)
7. Zoom al centro, la cara del rotor sale volando → **7. EJE EXCÉNTRICO** (corona, piñón fijo, excéntrica; el eje da 3 vueltas por cada vuelta del rotor)
8. La cámara sale, todo se cierra, el capot regresa y el carro se va por el puente → cierre.
