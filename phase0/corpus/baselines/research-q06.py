from collections import Counter
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

EX = Namespace("https://catalog.example.org/ns/")


def counts(path):
    graph = Graph().parse(path)
    pairs = {
        (department, publication)
        for publication in graph.subjects(RDF.type, EX.Publication)
        if str(graph.value(publication, EX.publicationYear)) == "2025"
        for researcher in graph.objects(publication, EX.contributor)
        for department in graph.objects(researcher, EX.memberOf)
    }
    return Counter(department for department, _ in pairs)
