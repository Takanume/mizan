"""Point d'entrée Streamlit à la racine.

Streamlit Community Cloud cherche par défaut un `streamlit_app.py` à la racine
du dépôt. Ce fichier ne fait que lancer la vraie application située dans
`app/streamlit_app.py`, pour que le déploiement fonctionne sans avoir à
configurer manuellement le « Main file path ».
"""

import runpy
from pathlib import Path

_APP = Path(__file__).resolve().parent / "app" / "streamlit_app.py"
runpy.run_path(str(_APP), run_name="__main__")
