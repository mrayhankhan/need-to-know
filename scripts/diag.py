"""Print what retrieval and access return for the demo questions."""
from ntk import access, brain, seed

seed.ensure_loaded()
for q in ["Why did Acme Corp's invoice go up in October?", "What are the engineering salary bands?", "How much runway do we have?"]:
    hits, cust = brain.retrieve("northwind", q)
    print("Q:", q, "| customers:", cust)
    for sid in hits:
        print("   ", sid, "| priya", access.can_read("northwind", "p_priya", sid), "| meera", access.can_read("northwind", "p_meera", sid))
