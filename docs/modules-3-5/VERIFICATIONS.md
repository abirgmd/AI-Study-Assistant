# Vérifications sur votre installation locale

1. Sans connexion, ouvrir `public/index.php` : redirection vers la connexion.
2. Créer un compte avec deux mots de passe différents : inscription refusée.
3. Créer un compte valide : accueil affiché et nom visible.
4. Dans MySQL, vérifier que `password_hash` contient un hachage, jamais le mot de passe.
5. Se déconnecter puis essayer un mauvais mot de passe : connexion refusée.
6. Se reconnecter : les documents et objectifs persistent.
7. Importer un TXT/PDF/DOCX valide ; télécharger le document depuis son titre.
8. Créer un second étudiant : aucun accès aux cours et objectifs du premier.
9. Avec le second compte, ouvrir le lien de téléchargement du premier : réponse 404.
10. Cocher un objectif, recharger : l’état est conservé pour la date du jour.
11. Réduire la fenêtre à une largeur mobile : formulaires et navigation restent utilisables.
12. Tester le quiz de démonstration : réponse expliquée, sans statistique enregistrée.

13. Service IA démarré : importer un vrai cours ; le statut « Prêt pour l’assistant » et une catégorie
    (ou « À classer » avec une suggestion) apparaissent.
14. Assistant de cours : une question sur le cours donne une réponse et des sources numérotées.
15. Une question hors sujet donne « Je ne trouve pas cette information dans vos cours. »
16. La même question une seconde fois affiche « réponse en cache ».
17. Avec le second étudiant, la même question ne renvoie aucune source du premier.
18. Cliquer sur la catégorie, la corriger : le badge affiche la nouvelle catégorie.
19. Arrêter le service IA puis importer un cours : l’import réussit, le cours est « Non indexé » ;
    une question affiche « L’assistant IA est momentanément indisponible ».
20. Relancer le service puis cliquer « Indexer » : le cours devient « Prêt pour l’assistant ».

## Test automatisé HTTP

Après installation, sur une base de test :

```sh
python tests/smoke.py http://localhost/ai-study-assistant/public/
```

Ou avec le serveur PHP local :

```sh
python tests/smoke.py http://localhost:8000/
```

Avec le service IA démarré : `python tests/smoke.py http://localhost:8000/ --with-ai`.

Le test crée deux comptes et un document, sans suppression automatique. Évitez les
exécutions répétées sur 15 minutes : la limitation des tentatives reste active.

## Validation de cette livraison (modules 3 et 5)

Exécuté le 25/10/2026 sur PHP 8.3 (serveur intégré), MariaDB 10.11 et le service IA en mode
hors ligne : `tests/smoke.py --with-ai` réussi, migration 002 rejouée deux fois sans erreur,
parcours de l’interface piloté avec Playwright (bureau et mobile) sans erreur console,
92 tests pytest réussis (couverture 96 %). Refaites ces vérifications sur votre XAMPP.
