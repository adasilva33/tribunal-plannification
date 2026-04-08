# Tribunal — Plannings

Application web Flask de gestion des plannings du tribunal de commerce.

## Lancer l'application

```bash
pip install -r requirements.txt
python app.py
```

L'application est accessible sur http://127.0.0.1:5000

## Compte administrateur par défaut

| Champ    | Valeur              |
|----------|---------------------|
| Email    | admin@tribunal.fr   |
| Mot de passe | admin123        |

> Pensez à changer ce mot de passe via Configuration → Juges après la mise en production.

## Réinitialiser la base de données

```bash
python app.py --reset
```
