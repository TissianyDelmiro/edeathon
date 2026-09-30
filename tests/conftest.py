import sys
from pathlib import Path

# Permite importar os módulos da raiz do projeto nos testes
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
