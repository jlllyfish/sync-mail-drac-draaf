#!/usr/bin/env python3
"""
Script d'envoi automatisé pour GitHub Actions avec gestion des dates améliorée
Fichier à créer : scripts/send_batch.py

Ce script reproduit la logique de votre app Flask pour l'envoi par lot
mais de manière autonome pour GitHub Actions, avec support des timestamps Unix.
"""

import os
import sys
import json
import requests
import logging
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any

# Configuration du logging
def setup_logging():
    """Configurer le système de logging"""
    # Créer le dossier logs s'il n'existe pas
    Path('logs').mkdir(exist_ok=True)
    
    # Configuration des handlers
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    # Handler pour la console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # Handler pour le fichier
    file_handler = logging.FileHandler(
        'logs/github-action.log', 
        mode='a', 
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # Configuration du logger principal
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Gestion des dates avec support des timestamps Unix
def parse_date_value(value: Any) -> Optional[date]:
    """
    Parser une valeur en date avec support étendu des timestamps Unix
    
    Gère :
    - Timestamps Unix en secondes (10 chiffres)
    - Timestamps Unix en millisecondes (13 chiffres)
    - Dates ISO (YYYY-MM-DD)
    - Dates françaises (DD/MM/YYYY)
    - Dates avec heures
    
    Args:
        value: Valeur à convertir en date
        
    Returns:
        date: Objet date Python ou None si échec
    """
    if not value:
        return None
    
    # Si c'est déjà un objet date
    if hasattr(value, 'date'):
        return value.date() if hasattr(value, 'date') else value
    
    # Timestamp Unix (entiers et flottants)
    if isinstance(value, (int, float)):
        try:
            # Si c'est un grand nombre, c'est probablement des millisecondes
            if value > 1e10:
                timestamp = value / 1000
            else:
                timestamp = value
            return datetime.fromtimestamp(timestamp).date()
        except (ValueError, OSError):
            pass
    
    # Convertir en string pour parsing
    date_str = str(value).strip()
    if not date_str:
        return None
    
    # String timestamp Unix
    if date_str.isdigit():
        try:
            timestamp = int(date_str)
            if timestamp > 1e10:
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp).date()
        except (ValueError, OSError):
            pass
    
    # Formats de date courants à essayer
    date_formats = [
        '%Y-%m-%d',           # 2023-12-25
        '%d/%m/%Y',           # 25/12/2023
        '%d-%m-%Y',           # 25-12-2023
        '%Y-%m-%d %H:%M:%S',  # 2023-12-25 14:30:00
        '%d/%m/%Y %H:%M:%S',  # 25/12/2023 14:30:00
        '%Y-%m-%dT%H:%M:%S',  # 2023-12-25T14:30:00 (ISO)
        '%Y-%m-%dT%H:%M:%SZ', # 2023-12-25T14:30:00Z (ISO avec Z)
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            return parsed_date.date()
        except ValueError:
            continue
    
    # Essayer avec regex pour les formats ISO avec millisecondes
    iso_pattern = r'(\d{4}-\d{2}-\d{2})'
    match = re.search(iso_pattern, date_str)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').date()
        except ValueError:
            pass
    
    logging.warning(f"Impossible de parser la date: {date_str}")
    return None

def format_date_french(value: Any) -> str:
    """
    Formater une date au format français (DD/MM/YYYY)
    
    Args:
        value: Valeur à formater (timestamp, date ISO, etc.)
        
    Returns:
        str: Date formatée en français ou chaîne vide si échec
    """
    if not value:
        return ""
    
    # Essayer de parser la date d'abord
    parsed_date = parse_date_value(value)
    if parsed_date:
        return parsed_date.strftime('%d/%m/%Y')
    
    # Si c'est déjà une chaîne formatée
    if isinstance(value, str):
        try:
            # Essayer de convertir depuis ISO
            if '-' in value:
                dt = datetime.strptime(value[:10], '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
        except ValueError:
            pass
    
    return str(value)

def check_date_filter(field_value: Any, operator: str, filter_value: str) -> bool:
    """
    Vérifier si une valeur correspond à un filtre de date
    
    Args:
        field_value: Valeur du champ à tester
        operator: Opérateur de comparaison ('date_before', 'date_after', etc.)
        filter_value: Valeur de comparaison (format YYYY-MM-DD ou YYYY-MM-DD|YYYY-MM-DD)
        
    Returns:
        bool: True si la valeur correspond au filtre
    """
    if not filter_value:
        return True
    
    try:
        # Convertir la valeur du champ en date
        field_date = parse_date_value(field_value)
        if not field_date:
            return False
        
        if operator == 'date_before':
            compare_date = datetime.strptime(filter_value, '%Y-%m-%d').date()
            return field_date < compare_date
            
        elif operator == 'date_after':
            compare_date = datetime.strptime(filter_value, '%Y-%m-%d').date()
            return field_date > compare_date
            
        elif operator == 'date_on':
            compare_date = datetime.strptime(filter_value, '%Y-%m-%d').date()
            return field_date == compare_date
            
        elif operator == 'date_between':
            if '|' not in filter_value:
                return False
            
            dates = filter_value.split('|')
            if len(dates) != 2:
                return False
            
            start_date = datetime.strptime(dates[0], '%Y-%m-%d').date()
            end_date = datetime.strptime(dates[1], '%Y-%m-%d').date()
            
            return start_date <= field_date <= end_date
    
    except (ValueError, TypeError) as e:
        logging.warning(f"Erreur lors de la comparaison de date: {e}")
        return False
    
    return False

def test_filter(field_value: Any, operator: str, value: str) -> bool:
    """
    Tester un filtre non-date sur une valeur
    
    Args:
        field_value: Valeur du champ
        operator: Opérateur de comparaison
        value: Valeur de comparaison
        
    Returns:
        bool: True si le filtre correspond
    """
    if operator == 'empty':
        return field_value is None or str(field_value).strip() == ''
    
    if operator == 'not_empty':
        return field_value is not None and str(field_value).strip() != ''
    
    if not value:
        return True
    
    # Convertir en chaîne pour la comparaison (opérateurs standards)
    field_str = str(field_value).lower() if field_value is not None else ''
    value_str = str(value).lower() if value else ''
    
    if operator == 'equals':
        return field_str == value_str
    elif operator == 'not_equals':
        return field_str != value_str
    elif operator == 'contains':
        return value_str in field_str
    elif operator == 'not_contains':
        return value_str not in field_str
    elif operator == 'starts_with':
        return field_str.startswith(value_str)
    elif operator == 'ends_with':
        return field_str.endswith(value_str)
    elif operator == 'greater_than':
        try:
            return float(field_value or 0) > float(value or 0)
        except (ValueError, TypeError):
            return False
    elif operator == 'less_than':
        try:
            return float(field_value or 0) < float(value or 0)
        except (ValueError, TypeError):
            return False
    elif operator == 'greater_equal':
        try:
            return float(field_value or 0) >= float(value or 0)
        except (ValueError, TypeError):
            return False
    elif operator == 'less_equal':
        try:
            return float(field_value or 0) <= float(value or 0)
        except (ValueError, TypeError):
            return False
    
    return True

def apply_filters(records: List[Dict], filters: List[Dict], filter_logic: str = 'AND') -> List[Dict]:
    """
    Appliquer les filtres aux enregistrements avec support amélioré des dates
    
    Args:
        records: Liste des enregistrements
        filters: Liste des filtres à appliquer
        filter_logic: Logique 'AND' ou 'OR'
        
    Returns:
        List[Dict]: Enregistrements filtrés
    """
    if not filters:
        return records
    
    filtered_records = []
    
    for record in records:
        fields = record.get('fields', {})
        
        # Évaluer chaque filtre
        filter_results = []
        for filter_config in filters:
            column = filter_config.get('column')
            operator = filter_config.get('operator')
            value = filter_config.get('value')
            
            field_value = fields.get(column)
            
            # Utiliser la fonction de test appropriée
            if operator.startswith('date_'):
                result = check_date_filter(field_value, operator, value)
            else:
                result = test_filter(field_value, operator, value)
            
            filter_results.append(result)
        
        # Appliquer la logique (AND/OR)
        if filter_logic == 'OR':
            # Au moins un filtre doit correspondre
            if any(filter_results):
                filtered_records.append(record)
        else:  # AND par défaut
            # Tous les filtres doivent correspondre
            if all(filter_results):
                filtered_records.append(record)
    
    return filtered_records
# Classes reprises de votre app Flask
class DSClient:
    """Client pour l'API Démarches Simplifiées"""
    
    def __init__(self, token: str):
        self.token = token
        self.endpoint = "https://www.demarches-simplifiees.fr/api/v2/graphql"
    
    def _make_request(self, query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Faire une requête GraphQL vers DS"""
        try:
            response = requests.post(
                self.endpoint,
                json={
                    'query': query,
                    'variables': variables or {}
                },
                headers={
                    'Authorization': f'Bearer {self.token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code != 200:
                return {'error': f'Erreur HTTP {response.status_code}: {response.text}'}
            
            data = response.json()
            
            if 'errors' in data:
                error_messages = [error.get('message', 'Erreur inconnue') for error in data['errors']]
                return {'error': f'Erreurs GraphQL: {", ".join(error_messages)}'}
            
            return data.get('data', {})
            
        except requests.exceptions.Timeout:
            return {'error': 'Timeout lors de la connexion à DS'}
        except requests.exceptions.ConnectionError:
            return {'error': 'Impossible de se connecter à DS'}
        except Exception as e:
            return {'error': f'Erreur lors de la requête: {str(e)}'}
    
    def send_message(self, dossier_id: str, instructeur_id: str, subject: str, body: str) -> Dict[str, Any]:
        """Envoyer un message à un dossier"""
        
        query = """
        mutation dossierEnvoyerMessage($input: DossierEnvoyerMessageInput!) {
          dossierEnvoyerMessage(input: $input) {
            message {
              id
              email
              body
              createdAt
            }
            errors {
              message
            }
          }
        }
        """
        
        variables = {
            "input": {
                "dossierId": dossier_id,
                "instructeurId": instructeur_id,
                "body": f"**{subject}**\n\n{body}"
            }
        }
        
        result = self._make_request(query, variables)
        
        if 'error' in result:
            return result
        
        message_result = result.get('dossierEnvoyerMessage', {})
        
        if message_result.get('errors'):
            error_messages = [error.get('message') for error in message_result['errors']]
            return {'error': f'Erreurs: {", ".join(error_messages)}'}
        
        return {
            'success': True,
            'message': message_result.get('message', {})
        }

class GristClient:
    """Client pour l'API Grist"""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://grist.numerique.gouv.fr/api"
    
    def _make_request(self, endpoint: str, method: str = 'GET', data: Dict = None) -> Dict[str, Any]:
        """Faire une requête vers l'API Grist"""
        try:
            url = f"{self.base_url}/{endpoint}"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            }
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, headers=headers, json=data, timeout=30)
            else:
                return {'error': f'Méthode HTTP non supportée: {method}'}
            
            if response.status_code not in [200, 201]:
                return {'error': f'Erreur HTTP {response.status_code}: {response.text}'}
            
            return response.json()
            
        except Exception as e:
            return {'error': f'Erreur Grist: {str(e)}'}
    
    def get_records(self, doc_id: str, table_name: str) -> Dict[str, Any]:
        """Récupérer les enregistrements d'une table"""
        endpoint = f"docs/{doc_id}/tables/{table_name}/records"
        return self._make_request(endpoint)
    
    def update_record(self, doc_id: str, table_name: str, record_id: int, data: Dict) -> Dict[str, Any]:
        """Mettre à jour un enregistrement"""
        endpoint = f"docs/{doc_id}/tables/{table_name}/records"
        update_data = {
            "records": [
                {
                    "id": record_id,
                    "fields": data
                }
            ]
        }
        return self._make_request(endpoint, 'PATCH', update_data)
class GitHubActionSender:
    """Client pour l'envoi par lot via GitHub Actions avec gestion des dates"""
    
    def __init__(self, config_file: str = 'config/public-config.json'):
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("🚀 Initialisation du script d'envoi automatisé avec gestion des dates")
        
        # Charger la configuration publique
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.logger.info(f"✅ Configuration chargée depuis {config_file}")
        except FileNotFoundError:
            self.logger.error(f"❌ Fichier de configuration non trouvé : {config_file}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ Erreur de format JSON : {e}")
            sys.exit(1)
        
        # Récupérer les secrets depuis les variables d'environnement
        self.ds_token = os.environ.get('DS_API_TOKEN')
        self.grist_token = os.environ.get('GRIST_API_TOKEN')
        self.dry_run = os.environ.get('DRY_RUN', 'false').lower() == 'true'
        self.force_send = os.environ.get('FORCE_SEND', 'false').lower() == 'true'
        
        if not self.ds_token:
            self.logger.error("❌ DS_API_TOKEN manquant dans les secrets GitHub")
            sys.exit(1)
        if not self.grist_token:
            self.logger.error("❌ GRIST_API_TOKEN manquant dans les secrets GitHub")
            sys.exit(1)
            
        self.logger.info("✅ Tokens récupérés depuis les secrets GitHub")
        if self.dry_run:
            self.logger.info("🧪 Mode DRY RUN activé - aucun message ne sera envoyé")
        if self.force_send:
            self.logger.info("🔄 Mode FORCE activé - renvoi des messages déjà envoyés")
        
        # Initialiser les clients
        self.ds_client = DSClient(self.ds_token)
        self.grist_client = GristClient(self.grist_token)
    
    def validate_config(self) -> bool:
        """Valider la configuration"""
        required_fields = [
            'demarche_number', 'message_subject', 'message_body', 
            'instructeur_id', 'grist_doc_id', 'grist_table'
        ]
        
        missing_fields = [field for field in required_fields if not self.config.get(field)]
        
        if missing_fields:
            self.logger.error(f"❌ Champs manquants dans la configuration : {missing_fields}")
            return False
            
        self.logger.info("✅ Configuration validée")
        return True
    
    def get_records_to_process(self) -> List[Dict]:
        """Récupérer les enregistrements à traiter depuis Grist avec filtres"""
        self.logger.info("📋 Récupération des enregistrements depuis Grist...")
        
        result = self.grist_client.get_records(
            self.config['grist_doc_id'],
            self.config['grist_table']
        )
        
        if 'error' in result:
            self.logger.error(f"❌ Erreur Grist : {result['error']}")
            return []
        
        records = result.get('records', [])
        self.logger.info(f"📊 {len(records)} enregistrements récupérés depuis Grist")
        
        # Appliquer les filtres configurés
        filters = self.config.get('filters', [])
        filter_logic = self.config.get('filter_logic', 'AND')
        
        if filters:
            self.logger.info(f"🔍 Application de {len(filters)} filtre(s) avec logique {filter_logic}")
            records = apply_filters(records, filters, filter_logic)
            self.logger.info(f"✅ {len(records)} enregistrements correspondent aux filtres")
        
        # Filtrer les enregistrements selon les critères d'envoi
        records_to_process = []
        
        for record in records:
            fields = record.get('fields', {})
            sync_mail = fields.get('sync_mail', '')
            dossier_id = fields.get('dossier_id', '')
            
            # Vérifier qu'on a un dossier_id
            if not dossier_id:
                continue
            
            # Si force_send, traiter tous les enregistrements
            if self.force_send:
                records_to_process.append(record)
                continue
            
            # Sinon, ne traiter que ceux qui ne sont pas déjà envoyés avec succès
            if sync_mail != 'success':
                records_to_process.append(record)
        
        self.logger.info(f"🎯 {len(records_to_process)} enregistrements à traiter")
        return records_to_process
    
    def format_message_with_dates(self, template: str, fields: Dict[str, Any]) -> str:
        """
        Formater un message en remplaçant les variables et en convertissant les dates
        
        Args:
            template: Template du message avec des variables {field_name}
            fields: Dictionnaire des champs de l'enregistrement
            
        Returns:
            str: Message formaté avec dates converties
        """
        formatted_template = template
        
        # Remplacer les variables par les valeurs formatées
        for field_name, field_value in fields.items():
            if field_value is not None:
                # Essayer de détecter et formater les dates
                formatted_value = format_date_french(field_value)
                
                # Si la conversion a échoué, garder la valeur originale
                if not formatted_value or formatted_value == str(field_value):
                    formatted_value = str(field_value)
                
                # Remplacer la variable dans le template
                formatted_template = formatted_template.replace(f'{{{field_name}}}', formatted_value)
        
        return formatted_template
    
    def send_message_to_record(self, record: Dict) -> Dict[str, Any]:
        """Envoyer un message à un enregistrement spécifique avec gestion des dates"""
        fields = record.get('fields', {})
        record_id = record.get('id')
        dossier_id = str(fields.get('dossier_id', ''))
        
        if not dossier_id:
            return {'error': 'dossier_id manquant'}
        
        # Personnaliser le message avec les variables et conversion des dates
        subject = self.format_message_with_dates(self.config['message_subject'], fields)
        body = self.format_message_with_dates(self.config['message_body'], fields)
        
        self.logger.info(f"📧 Envoi message au dossier {dossier_id}")
        self.logger.debug(f"   Sujet: {subject[:50]}...")
        
        if self.dry_run:
            self.logger.info(f"🧪 [DRY RUN] Message qui serait envoyé au dossier {dossier_id}")
            return {'success': True, 'dry_run': True}
        
        # Envoyer le message
        result = self.ds_client.send_message(
            dossier_id,
            self.config['instructeur_id'],
            subject,
            body
        )
        
        # Mettre à jour Grist selon le résultat
        now = datetime.now().isoformat()
        
        if result.get('success'):
            # Succès
            update_data = {
                'sync_mail': 'success',
                'sync_date': now,
                'sync_error': ''
            }
            self.logger.info(f"✅ Message envoyé avec succès au dossier {dossier_id}")
        else:
            # Erreur
            error_msg = result.get('error', 'Erreur inconnue')
            update_data = {
                'sync_mail': 'failure',
                'sync_date': now,
                'sync_error': error_msg[:500]  # Limiter la taille du message d'erreur
            }
            self.logger.error(f"❌ Erreur envoi dossier {dossier_id}: {error_msg}")
        
        # Mettre à jour l'enregistrement dans Grist
        if not self.dry_run:
            update_result = self.grist_client.update_record(
                self.config['grist_doc_id'],
                self.config['grist_table'],
                record_id,
                update_data
            )
            
            if update_result is None:
                self.logger.warning(f"⚠️ Mise à jour Grist pour {dossier_id}: réponse vide")
            elif isinstance(update_result, dict) and 'error' in update_result:
                self.logger.warning(f"⚠️ Erreur mise à jour Grist pour {dossier_id}: {update_result['error']}")
            else:
                self.logger.debug(f"✅ Mise à jour Grist réussie pour {dossier_id}")
        
        return result
    
    def send_batch(self):
        """Lancer l'envoi par lot avec gestion avancée des dates"""
        self.logger.info("📧 Démarrage de l'envoi par lot automatisé avec gestion des dates")
        
        if not self.validate_config():
            sys.exit(1)
        
        # Log des informations de configuration (sans les tokens)
        self.logger.info("📋 Configuration :")
        self.logger.info(f"   • Démarche : {self.config.get('demarche_number')}")
        self.logger.info(f"   • Instructeur : {self.config.get('instructeur_id')}")
        self.logger.info(f"   • Document Grist : {self.config.get('grist_doc_id')}")
        self.logger.info(f"   • Table : {self.config.get('grist_table')}")
        self.logger.info(f"   • Filtres : {len(self.config.get('filters', []))} configurés")
        
        # Récupérer les enregistrements à traiter
        records = self.get_records_to_process()
        
        if not records:
            self.logger.info("ℹ️ Aucun enregistrement à traiter")
            return {
                'success': True,
                'total_records': 0,
                'success_count': 0,
                'error_count': 0,
                'already_sent_count': 0
            }
        
        # Traiter chaque enregistrement
        results = {
            'total_records': len(records),
            'success_count': 0,
            'error_count': 0,
            'already_sent_count': 0,
            'details': []
        }
        
        for i, record in enumerate(records, 1):
            fields = record.get('fields', {})
            dossier_id = fields.get('dossier_id', 'N/A')
            
            self.logger.info(f"🔄 Traitement {i}/{len(records)} - Dossier {dossier_id}")
            
            # Log des champs de date détectés pour debug
            date_fields = []
            for field_name, field_value in fields.items():
                if field_value and parse_date_value(field_value):
                    formatted_date = format_date_french(field_value)
                    date_fields.append(f"{field_name}: {field_value} → {formatted_date}")
            
            if date_fields:
                self.logger.debug(f"   📅 Dates détectées: {', '.join(date_fields[:3])}")
            
            result = self.send_message_to_record(record)
            
            if result.get('success'):
                if result.get('dry_run'):
                    results['success_count'] += 1
                else:
                    results['success_count'] += 1
            else:
                results['error_count'] += 1
                results['details'].append({
                    'dossier_id': dossier_id,
                    'error': result.get('error', 'Erreur inconnue')
                })
        
        # Log final
        self.logger.info("📊 Résultats de l'envoi :")
        self.logger.info(f"   • Total traité : {results['total_records']}")
        self.logger.info(f"   • ✅ Succès : {results['success_count']}")
        self.logger.info(f"   • ❌ Erreurs : {results['error_count']}")
        
        # Sauvegarder les résultats
        results_file = f"logs/results-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        self.logger.info(f"💾 Résultats sauvegardés dans {results_file}")
        
        if results['error_count'] > 0:
            self.logger.warning(f"⚠️ {results['error_count']} erreur(s) détectée(s)")
            # Décider si on fait échouer le workflow ou non
            # return sys.exit(1)  # Décommentez pour faire échouer en cas d'erreur
        else:
            self.logger.info("✅ Envoi terminé avec succès")
        
        return results

def main():
    """Point d'entrée principal"""
    logger = setup_logging()
    
    try:
        logger.info("=" * 60)
        logger.info("🚀 DÉMARRAGE DU SCRIPT D'ENVOI AUTOMATISÉ AVEC GESTION DES DATES")
        logger.info("=" * 60)
        
        sender = GitHubActionSender()
        result = sender.send_batch()
        
        logger.info("=" * 60)
        logger.info("🎉 SCRIPT TERMINÉ AVEC SUCCÈS")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("⛔ Script interrompu par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Erreur fatale : {str(e)}")
        logger.exception("Détails de l'erreur :")
        sys.exit(1)

if __name__ == "__main__":
    main()
