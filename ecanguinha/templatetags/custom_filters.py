# ecanguinha/templatetags/custom_filters.py

from django import template

register = template.Library()

@register.filter(name='dict_get')
def dict_get(dicionario, chave):
    """
    Retorna o valor associado a uma chave em um dicionário.
    Se a chave não existir, retorna uma lista vazia.
    """
    if isinstance(dicionario, dict):
        return dicionario.get(chave, [])
    return []
