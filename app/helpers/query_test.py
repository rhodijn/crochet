import requests

query = """
PREFIX crm: <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?obj ?label WHERE {
  ?obj a crm:E22_Human-Made_Object .
  OPTIONAL { ?obj rdfs:label ?label }
} LIMIT 20
"""

r = requests.get(
    "https://sparql.digital.skkg.ch",
    params={"query": query},
    headers={"Accept": "application/sparql-results+json"},
)
for row in r.json()["results"]["bindings"]:
    print(row["obj"]["value"], row.get("label", {}).get("value"))