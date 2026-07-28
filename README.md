# Yako OCR

API FastAPI + interface web pour extraire les champs des documents d’identité ivoiriens (CNI, passeport, CMU, permis).

## Lancer en local

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Ouvrir : http://127.0.0.1:8000  
Santé : http://127.0.0.1:8000/health

## Déploiement cPanel (Setup Python App)

### 1. Créer l’application

Dans **cPanel → Setup Python App** (ou Application Manager) :

| Champ | Valeur |
|--------|--------|
| Python version | **3.10** ou **3.11** (recommandé) |
| Application root | dossier du projet (ex. `yako_ocr`) |
| Application URL | votre domaine / sous-domaine |
| Application startup file | `passenger_wsgi.py` |
| Application entry point | `application` |

Créer l’app, puis **uploader** le code (Git, FTP ou File Manager) dans le *Application root*.

> Si cPanel génère un `passenger_wsgi.py` vide, **remplacez-le** par celui du dépôt.

### 2. Installer les dépendances

Dans Setup Python App, ouvrir le terminal / activer le venv affiché, puis :

```bash
cd ~/chemin/vers/yako_ocr
source /home/USER/virtualenv/chemin/bin/activate   # commande fournie par cPanel
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Variables d’environnement (optionnel)

Dans Setup Python App → Environment variables, ou fichier `.env` (voir `.env.example`) :

- `OCR_BACKEND=hybrid` (ou `paddle` / `rapid`)
- `OCR_WARMUP=0` (recommandé sur cPanel pour éviter un timeout au démarrage)

### 4. Redémarrer

Bouton **Restart** dans Setup Python App.

Vérifier :

- `https://votre-domaine/health` → `{"status":"ok"}`
- `https://votre-domaine/` → interface Yako OCR

Le SSL est géré par cPanel (AutoSSL) : **pas besoin** de `cert.pem` / `key.pem`.

### Notes importantes

- Premier appel OCR peut être **lent** (chargement des modèles).
- L’hébergeur doit autoriser des paquets natifs (`opencv`, `paddle`, `onnxruntime`). En cas d’échec `pip`, contacter le support ou utiliser un VPS.
- Ne pas uploader `.venv`, `__pycache__`, ni fichiers `.pem`.

## Structure

```
passenger_wsgi.py   # entrée cPanel (ASGI → WSGI via a2wsgi)
app/                # API FastAPI + OCR
frontend/           # UI
requirements.txt
.env.example
```
