"""UI prose is not a business identity or an instruction to create records."""
import re
from html import unescape
from app.services.chat_turns import norm

def welcome_echo(text):
    value=re.sub(r'\s+',' ',norm(unescape(text))).strip(' .!')
    return value in {
        norm('Bonjour ! Décrivez l’article ou le fournisseur souhaité. Je préparerai sa fiche pour votre confirmation. Aucune création ne sera lancée sans votre approbation.').strip(' .!'),
        norm('Bonjour ! Indiquez le nom et les informations du fournisseur. Je préparerai sa fiche dans TEST pour votre confirmation.').strip(' .!'),
    }

def invalid_supplier_name(value):
    name=norm(value or '').strip(' .!')
    return name in {'votre confirmation','votre approbation','suivant dans le systeme','le fournisseur souhaite'} or bool(re.match(r'^(?:bghit|bghina|3afak|ma3reftch|chno|wach)\s+\w',name))
