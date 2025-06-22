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

@register.filter(name='sum_precos')
def sum_precos(lista_produtos):
    """
    Soma os preços de uma lista de produtos, onde cada item deve ser um dicionário
    com a chave 'preco'.
    """
    if not lista_produtos:
        return 0.0
    return sum(p.get('preco', 0) for p in lista_produtos if isinstance(p, dict))
