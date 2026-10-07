from django.conf import settings


def map_tiles(request):
    """Disponibiliza a URL (e a atribuição) dos tiles do mapa a todos os templates."""
    return {
        "MAP_TILE_URL": settings.MAP_TILE_URL,
        "MAP_TILE_ATTRIBUTION": settings.MAP_TILE_ATTRIBUTION,
    }
