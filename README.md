# tradusmart

Procesamiento automático de subtítulos `.srt` para videos en inglés, generando versiones en español listas para usar en el video final.

El proyecto toma subtítulos `.srt` generados automáticamente, los traduce al español, mejora su redacción y ajusta su sincronización para que funcionen correctamente al incorporarlos o quemarlos en el video.

## Objetivo

Generar subtítulos en español que:
- sean claros y naturales (no traducción literal)
- mantengan una buena sincronización con el video

Actualmente, el principal desafío del proyecto es el ajuste del timing de los subtítulos.

## Estructura de trabajo (local)
- `C:\Users\javier\Desktop\xJavier\videos NDS\` → Dentro de esta carpeta estan todas las demas subcarpetas 
- `Videos/` → videos originales  
- `transcripciones_srt/` → SRT en inglés (originales)  
- `paratraducir/` → SRT a procesar  
- `traducidos/` → SRT en español (salida)  
- `scripts/` → scripts del proyecto  

## Flujo de trabajo

1. Copiar un `.srt` en inglés a `paratraducir`
2. Ejecutar el script
3. Traducción + mejora de redacción
4. Ajuste de tiempos
5. Salida en `traducidos`
6. Uso del SRT en el video final

## Estructura del repositorio

- `scripts/`  
  Contiene las distintas versiones de los scripts de procesamiento.

- `srt_in/`  
  Archivo(s) `.srt` en inglés utilizados como entrada de prueba.

- `srt_out/`  
  Resultados generados por cada versión del script, para comparación.  
  Ejemplo: `v1_output.srt`, `v2_output.srt`, etc.

- `README.md`  
  Documentación del proyecto.

> Nota: el procesamiento real del proyecto se realiza sobre carpetas locales (no incluidas en este repositorio).
