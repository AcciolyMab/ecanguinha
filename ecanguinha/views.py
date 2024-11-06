from django.shortcuts import render
from django.http import HttpResponse


# Create your views here.
def home(request):
    if request.method == "GET":
        return render(request, 'home.html')
    else:
        nome = request.POST['nome']
        return HttpResponse(nome)

def localizacao(request):
    return render(request, 'localizacao.html')  # Nova view para sobre

def about(request):
    return render(request, 'about.html')  # Nova view para sobre

def contact(request):
    return render(request, 'contact.html')  # Nova view para contato