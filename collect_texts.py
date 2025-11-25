#!/usr/bin/env python3
import os, sys

root = r"F:\Programs\PythonProject\VideoDuplicateCleaner\src"   # <-- замените
out = r"F:\Programs\PythonProject\VideoDuplicateCleaner\project_all.txt"

# Список кодировок для попытки декодирования
encodings = ['utf-8', 'cp1251', 'latin-1']

if os.path.exists(out):
    os.remove(out)

with open(out, 'w', encoding='utf-8') as fout:
    for dirpath, dirs, files in os.walk(root):
        files.sort()
        for fn in files:
            if fn.lower().endswith('.md'):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            fout.write(rel + '\n\n')
            try:
                raw = open(full, 'rb').read()
                for enc in encodings:
                    try:
                        text = raw.decode(enc)
                        break
                    except Exception:
                        text = None
                if text is None:
                    fout.write('[UNREADABLE OR BINARY - skipped]\n\n\n')
                else:
                    fout.write(text + '\n\n\n')
            except Exception as e:
                fout.write(f'[ERROR reading file: {e}]\n\n\n')

print("Готово — файл:", out)
