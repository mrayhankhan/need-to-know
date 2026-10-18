# Every Cypher query Need-to-Know depends on

All queries run on FalkorDB. Parameters are passed as query parameters (never string-formatted),
so FalkorDB can cache the plans. Read paths use `GRAPH.RO_QUERY`. `MAX_HOPS` is 8.

## Indexes (created before loading, `ntk/seed.py`)

```cypher
CREATE INDEX FOR (n:Principal) ON (n.id)     // also Space, Doc, Section, Customer, Case, Decision, Episode, Note
CREATE FULLTEXT INDEX FOR (n:Section) ON (n.text, n.label)
```

## 1. Access: who can read what (`ntk/access.py`)

**Resolve every grant a person or agent holds, through any depth of nested groups.** This one
traversal is the heart of the product: it runs once per question, per agent step and per check.

```cypher
MATCH (p:Principal {id:$pid})-[:MEMBER_OF*0..8]->(g:Principal)-[:CAN_READ]->(t)
RETURN DISTINCT t.id
```

A passage is readable if its id is in that set, or (when the passage is not `restricted`) its
document or the document's space is.

**Baseline used only by the benchmark ("flat list"): direct groups only.**

```cypher
MATCH (p:Principal {id:$pid})-[:MEMBER_OF*0..1]->(g:Principal)-[:CAN_READ]->(t)
RETURN DISTINCT t.id
```

**Why can I see this? The shortest chain of memberships behind a grant.**

```cypher
MATCH path = (p:Principal {id:$pid})-[:MEMBER_OF*0..8]->(g:Principal)-[r:CAN_READ]->(t)
WHERE t.id IN $targets
RETURN [n IN nodes(path) | n.name], [n IN nodes(path) | labels(n)[0]], [n IN nodes(path) | n.id],
       t.id, r.granted_by, r.granted_at, r.reason, length(path) AS hops
ORDER BY hops ASC LIMIT 1
```

**Who could grant a redacted passage** (shown on the redaction bar):

```cypher
MATCH (g:Principal)-[r:CAN_READ]->(t) WHERE t.id IN $targets
RETURN DISTINCT g.id, g.name, labels(g)[0]
```

**Everyone who can open a document** (reverse traversal):

```cypher
MATCH (p:Person)-[:MEMBER_OF*0..8]->(g:Principal)-[:CAN_READ]->(t)
WHERE t.id IN $targets
RETURN DISTINCT p.id
```

**Document catalog** (cached per graph):

```cypher
MATCH (s:Section)-[:PART_OF]->(d:Doc)-[:IN]->(sp:Space)
OPTIONAL MATCH (o:Person)-[:OWNS]->(d)
RETURN s.id, s.label, s.text, s.restricted, d.id, d.title, d.kind, d.updated, sp.id, sp.name, o.name, o.id
```

## 2. Answering (`ntk/brain.py`)

```cypher
// full-text candidates (RediSearch syntax, OR of the question's keywords)
CALL db.idx.fulltext.queryNodes('Section', $q) YIELD node, score
RETURN node.id, score ORDER BY score DESC LIMIT 24

// passages about a customer named in the question
MATCH (c:Customer)<-[:MENTIONS]-(s:Section) WHERE c.id IN $customers RETURN s.id

// decisions behind the facts, and who made them
MATCH (d:Doc)-[:DOCUMENTS]->(x:Decision)-[:DECIDED_IN]->(src:Doc)
WHERE d.id IN $docs OR src.id IN $docs
MATCH (p:Person)-[:MADE]->(x)
RETURN DISTINCT x.id, x.summary, x.date, p.name, src.id, src.title, d.id, d.title
```

## 3. Private memory (`ntk/memory.py`)

```cypher
// write: the episode hangs off its owner
MATCH (o:Principal {id:$pid})
CREATE (o)-[:REMEMBERS]->(e:Episode {id:$id, kind:$kind, text:$text, ts:$ts})
WITH e UNWIND $customers AS cid MATCH (c:Customer {id:cid}) CREATE (e)-[:MENTIONS]->(c)

// read: always starts from the requester's own node
MATCH (me:Principal {id:$pid})-[:REMEMBERS]->(e:Episode)
OPTIONAL MATCH (e)-[:MENTIONS]->(c:Customer)
WITH e, collect(c.name) AS about, collect(c.id) AS cids
WHERE size($customers) = 0 OR any(x IN cids WHERE x IN $customers)
RETURN e.id, e.kind, e.text, e.ts, about ORDER BY e.ts DESC LIMIT $limit

// privacy proof: there is no path from me to your memories
MATCH (me:Principal {id:$asker})-[:REMEMBERS]->(e:Episode)<-[:REMEMBERS]-(owner:Principal {id:$owner})
RETURN count(e)
```

## 4. Agents sharing a case (`ntk/agents.py`)

```cypher
// a note on the shared case; Finance-only notes get their own grants
MATCH (c:Case {id:$case}), (a:Principal {id:$author})
CREATE (a)-[:WROTE]->(n:Note {id:$id, text:$text, customer_text:$ct, restricted:$r, ts:$ts})-[:ON]->(c)

MATCH (w:Principal {id:$who}), (n:Note {id:$id})
CREATE (w)-[:CAN_READ {granted_by:$by, granted_at:$at, reason:'Finance-only note'}]->(n)

// handoff between agents, and the case's shared state
MATCH (a:Principal {id:$a}), (b:Principal {id:$b}), (c:Case {id:$case})
CREATE (a)-[:HANDED_OFF {case:$case, ts:$ts, reason:$reason, step:$step}]->(b)
SET c.claimed_by = $b, c.status = 'with ' + b.name

// reading the case back
MATCH (n:Note)-[:ON]->(c:Case {id:$case}) MATCH (a:Principal)-[:WROTE]->(n)
RETURN n.id, n.text, n.customer_text, n.restricted, n.ts, a.id, a.name ORDER BY n.ts, n.id
```

## 5. Oversharing and drift (`ntk/scan.py`)

```cypher
// documents with an intended audience
MATCH (d:Doc) WHERE size(d.intended) > 0 RETURN d.id, d.title, d.space, d.intended

// per grant: everyone it lets in (to find the grant that causes the overshare)
MATCH (g:Principal)-[r:CAN_READ]->(t) WHERE t.id IN $targets
OPTIONAL MATCH (p:Person)-[:MEMBER_OF*0..8]->(g)
RETURN g.id, g.name, labels(g)[0], t.id, r.granted_by, r.granted_at, r.reason, collect(DISTINCT p.id)

// who is supposed to read it
MATCH (p:Person)-[:MEMBER_OF*0..8]->(g:Principal) WHERE g.id IN $intended RETURN DISTINCT p.id

// people who changed teams but are still in their old team's group
MATCH (p:Person)-[:MEMBER_OF]->(g:Group {kind:'team'})
WHERE g.team <> p.team AND p.moved_from IS NOT NULL
RETURN p.id, p.name, p.title, p.team, p.moved_from, p.moved_at, g.id, g.name
```

**Testing a fix without touching the company:** `GRAPH.COPY northwind northwind__fork__<id>`,
then on the fork:

```cypher
MATCH (g:Principal {id:$gid})-[r:CAN_READ]->(t {id:$tid}) DELETE r
```

Readers are recomputed on the fork and compared with the intended audience. The fork is then
deleted with `GRAPH.DELETE`. Only after a person approves is the same change applied live, with
a decision record:

```cypher
MATCH (p:Principal {id:$approver})
CREATE (p)-[:MADE]->(x:Decision {id:$id, summary:$summary, date:$date, kind:'access-change', reason:$reason})
WITH x MATCH (t {id:$target}) CREATE (x)-[:CHANGED]->(t)
```

## 6. Multi-tenancy

Each company is its own graph in the same FalkorDB instance (`northwind`, `bluefin`), so a query
for one company cannot touch another's nodes.
