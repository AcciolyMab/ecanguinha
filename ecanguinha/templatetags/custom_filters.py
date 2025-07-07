from django import template

register = template.Library()

@register.filter(name='dict_get')
def dict_get(dicionario, chave):
    """
    Retorna o valor associado a uma chave em um dicionário.
    Se a chave não existir, retorna uma lista vazia.
    """
    return dicionario.get(chave, []) if isinstance(dicionario, dict) else []

@register.filter(name='sum_precos')
def sum_precos(lista_produtos):
    """
    Soma os preços de uma lista de produtos, onde cada item deve ser um dicionário
    com a chave 'preco'. Retorna 0.0 se a lista estiver vazia ou os itens não forem dicionários.
    """
    if not lista_produtos:
        return 0.0
    return sum(
        (item.get('preco', 0) for item in lista_produtos if isinstance(item, dict))
    )

@register.filter
def subtrair(valor1, valor2):
    """
    Subtrai dois valores numéricos, retornando 0 em caso de erro de conversão.
    """
    try:
        return float(valor1) - float(valor2)
    except (ValueError, TypeError):
        return 0