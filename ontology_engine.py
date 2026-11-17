"""Read the Protégé export and index the incident model for the agents."""

from collections import deque
from pathlib import Path
import re
import shutil

from owlready2 import World, sync_reasoner
from rdflib import Graph, Namespace, OWL, RDF, RDFS


def label(identifier: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[A-Za-z])(?=\d)", " ", identifier)


def local_name(iri) -> str:
    return str(iri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


class Ontology:
    def __init__(self, path: Path):
        graph = Graph().parse(path, format="xml")
        dependency = next(
            prop for prop in graph.subjects(RDF.type, OWL.ObjectProperty)
            if local_name(prop) == "directlyDependsOn"
        )
        iq = Namespace(str(dependency).removesuffix("directlyDependsOn"))
        self.source = path.name
        self.classes = len(set(graph.subjects(RDF.type, OWL.Class)))
        self.reasoner = "RDF property paths"
        inferred = graph
        if shutil.which("java"):
            world = World()
            try:
                with path.open("rb") as source:
                    world.get_ontology(str(iq)).load(fileobj=source)
                sync_reasoner(world, infer_property_values=True, debug=0)
                inferred = Graph()
                for triple in world.as_rdflib_graph():
                    inferred.add(triple)
                self.reasoner = "HermiT + RDF property paths"
            finally:
                world.close()

        def instances(kind):
            rows = inferred.query(
                "SELECT DISTINCT ?entity WHERE { ?entity rdf:type/rdfs:subClassOf* ?kind }",
                initBindings={"kind": iq[kind]}, initNs={"rdf": RDF, "rdfs": RDFS},
            )
            return sorted({local_name(row[0]) for row in rows if str(row[0]).startswith(str(iq))})

        def objects(identifier, property_name):
            return sorted(local_name(value) for value in graph.objects(iq[identifier], iq[property_name]))

        def literal(identifier, property_name):
            return str(graph.value(iq[identifier], iq[property_name], default=""))

        self.services = instances("Service")
        self.tests = {key: literal(key, "hasTestProcedure") for key in instances("DiagnosticTest")}
        self.symptoms = {
            key: {"description": literal(key, "hasDescription"), "code": literal(key, "hasErrorCode")}
            for key in instances("Symptom")
        }
        self.direct = {
            key: sorted(set(objects(key, "directlyDependsOn") + objects(key, "dependsOn")))
            for key in self.services
        }
        rows = inferred.query(
            "SELECT DISTINCT ?service ?dependency WHERE { "
            "?service (iq:directlyDependsOn|iq:dependsOn|^iq:requiredBy)+ ?dependency }",
            initNs={"iq": iq},
        )
        self.dependencies = {key: set() for key in self.services}
        for row in rows:
            service, dependency = map(local_name, row)
            if service in self.dependencies and service != dependency:
                self.dependencies[service].add(dependency)

        roots = set(instances("RootCause"))
        self.faults = {}
        for key in instances("Fault"):
            severity = objects(key, "hasSeverity")
            self.faults[key] = {
                "id": key,
                "root": key in roots,
                "severity": severity[0] if severity else None,
                "services": objects(key, "affectsService"),
                "tests": objects(key, "diagnosedBy"),
                "causes": objects(key, "mayBeCausedBy"),
                "symptoms": objects(key, "hasSymptom"),
                "solutions": [
                    {"id": item, "text": literal(item, "hasInstructions")}
                    for item in objects(key, "resolvedBy") if literal(item, "hasInstructions")
                ],
            }

    def dependency_path(self, start, target):
        pending = deque([[start]])
        seen = {start}
        while pending:
            path = pending.popleft()
            if path[-1] == target:
                return path
            for dependency in self.direct.get(path[-1], []):
                if dependency not in seen:
                    seen.add(dependency)
                    pending.append([*path, dependency])
        return []

    def affected(self, fault):
        direct = set(fault["services"])
        return sorted(direct | {
            service for service, dependencies in self.dependencies.items()
            if direct & dependencies
        })
