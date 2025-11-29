from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from .neo4j_conn import get_driver
from .models import UserCreate, TransactionCreate, GraphResponse, Node, RelationshipEdge
from .data_gen import create_constraints, generate_sample_data

app = FastAPI(title="User & Transactions Relationship Visualization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    driver = get_driver()
    with driver.session() as session:
        session.execute_write(create_constraints)


@app.post("/users", status_code=201)
def add_or_update_user(user: UserCreate):
    driver = get_driver()
    with driver.session() as session:
        session.run(
            """
            MERGE (u:User {user_id: $user_id})
            SET u.name = $name,
                u.email = $email,
                u.phone = $phone,
                u.address = $address,
                u.payment_method = $payment_method
            """,
            **user.dict(),
        )
    return {"message": "User added/updated"}


@app.post("/transactions", status_code=201)
def add_or_update_transaction(tx: TransactionCreate):
    driver = get_driver()
    with driver.session() as session:
        result = session.run("MATCH (u:User {user_id: $uid}) RETURN u LIMIT 1", uid=tx.from_user)
        if not result.single():
            raise HTTPException(status_code=404, detail="from_user not found")

        result = session.run("MATCH (u:User {user_id: $uid}) RETURN u LIMIT 1", uid=tx.to_user)
        if not result.single():
            raise HTTPException(status_code=404, detail="to_user not found")

        session.run(
            """
            MERGE (t:Transaction {tx_id: $tx_id})
            SET t.amount = $amount,
                t.currency = $currency,
                t.timestamp = $timestamp,
                t.ip = $ip,
                t.device_id = $device_id
            """,
            tx_id=tx.tx_id,
            amount=tx.amount,
            currency=tx.currency,
            timestamp=tx.timestamp.isoformat(),
            ip=tx.ip,
            device_id=tx.device_id,
        )

        session.run(
            """
            MATCH (u_from:User {user_id: $from_user}), (t:Transaction {tx_id: $tx_id})
            MERGE (u_from)-[:SENT]->(t)
            """,
            from_user=tx.from_user,
            tx_id=tx.tx_id,
        )

        session.run(
            """
            MATCH (u_to:User {user_id: $to_user}), (t:Transaction {tx_id: $tx_id})
            MERGE (u_to)-[:RECEIVED]->(t)
            """,
            to_user=tx.to_user,
            tx_id=tx.tx_id,
        )

    return {"message": "Transaction added/updated"}


@app.get("/users")
def list_users(limit: int = 100, skip: int = 0):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:User)
            RETURN u.user_id AS user_id, u.name AS name, u.email AS email,
                   u.phone AS phone, u.address AS address, u.payment_method AS payment_method
            SKIP $skip LIMIT $limit
            """,
            skip=skip,
            limit=limit,
        )
        return [record.data() for record in result]


@app.get("/transactions")
def list_transactions(limit: int = 100, skip: int = 0):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (t:Transaction)
            RETURN t.tx_id AS tx_id, t.amount AS amount, t.currency AS currency,
                   t.timestamp AS timestamp, t.ip AS ip, t.device_id AS device_id
            SKIP $skip LIMIT $limit
            """,
            skip=skip,
            limit=limit,
        )
        return [record.data() for record in result]


@app.get("/relationships/user/{user_id}", response_model=GraphResponse)
def get_user_relationships(user_id: str):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (u:User {user_id: $user_id})
            OPTIONAL MATCH (u)-[rel1]-(other)
            OPTIONAL MATCH (u)-[:SENT|RECEIVED]->(t:Transaction)
            RETURN u, collect(DISTINCT other) as others, collect(DISTINCT t) as txs, collect(DISTINCT rel1) as rels
            """,
            user_id=user_id,
        )

        record = result.single()
        if not record or record["u"] is None:
            raise HTTPException(status_code=404, detail="User not found")

        u_node = record["u"]
        others = record["others"]
        txs = record["txs"]

        nodes_map = {}
        edges: List[RelationshipEdge] = []

        def add_node(node, kind):
            nid = node["user_id"] if kind == "user" else node["tx_id"]
            if nid not in nodes_map:
                nodes_map[nid] = Node(
                    id=nid,
                    label=node.get("name") if kind == "user" else nid,
                    kind=kind,
                )

        add_node(u_node, "user")

        for o in others:
            if o is None:
                continue
            kind = "user" if "user_id" in o else "transaction"
            add_node(o, kind)

        for t in txs:
            if t is None:
                continue
            add_node(t, "transaction")

        # query edges more explicitly
        rel_result = session.run(
            """
            MATCH (u:User {user_id: $user_id})-[r]-(n)
            RETURN u.user_id AS from, n,
                   type(r) AS rel_type
            """,
            user_id=user_id,
        )

        for r in rel_result:
            n = r["n"]
            rel_type = r["rel_type"]
            if "user_id" in n:
                target_id = n["user_id"]
            else:
                target_id = n["tx_id"]

            edges.append(
                RelationshipEdge(
                    source=r["from"],
                    target=target_id,
                    type=rel_type,
                )
            )

        return GraphResponse(nodes=list(nodes_map.values()), edges=edges)


@app.get("/relationships/transaction/{tx_id}", response_model=GraphResponse)
def get_transaction_relationships(tx_id: str):
    driver = get_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (t:Transaction {tx_id: $tx_id})
            OPTIONAL MATCH (t)-[r]-(n)
            RETURN t, collect(DISTINCT n) as neighbors
            """,
            tx_id=tx_id,
        )

        record = result.single()
        if not record or record["t"] is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        t_node = record["t"]
        neighbors = record["neighbors"]

        nodes_map = {}
        edges: List[RelationshipEdge] = []

        def add_node(node, kind):
            nid = node["user_id"] if kind == "user" else node["tx_id"]
            if nid not in nodes_map:
                nodes_map[nid] = Node(
                    id=nid,
                    label=node.get("name") if kind == "user" else nid,
                    kind=kind,
                )

        add_node(t_node, "transaction")

        for n in neighbors:
            if n is None:
                continue
            if "user_id" in n:
                kind = "user"
                nid = n["user_id"]
            else:
                kind = "transaction"
                nid = n["tx_id"]
            add_node(n, kind)

        rel_result = session.run(
            """
            MATCH (t:Transaction {tx_id: $tx_id})-[r]-(n)
            RETURN t.tx_id AS from, n,
                   type(r) AS rel_type
            """,
            tx_id=tx_id,
        )

        for r in rel_result:
            n = r["n"]
            rel_type = r["rel_type"]
            if "user_id" in n:
                target_id = n["user_id"]
            else:
                target_id = n["tx_id"]
            edges.append(
                RelationshipEdge(
                    source=r["from"],
                    target=target_id,
                    type=rel_type,
                )
            )

        return GraphResponse(nodes=list(nodes_map.values()), edges=edges)


from fastapi import BackgroundTasks

def _run_generation(users, transactions, batch_size, create_shared_links):
    driver = get_driver()
    # use a single session to call the generate function directly
    with driver.session() as session:
        # we use the new generate_sample_data which expects a session-like object
        # (we pass the session to the function)
        from .data_gen import generate_sample_data
        generate_sample_data(session, user_count=users, tx_count=transactions, batch_size=batch_size, create_shared_links=create_shared_links)

@app.post("/generate-data")
def generate_data(background_tasks: BackgroundTasks, users: int = 200, transactions: int = 2000, batch_size: int = 1000, create_links: bool = False):
    """
    Starts generation in background. Returns immediately.
    Use docker logs (or console) to follow progress printed by the generator.
    """
    background_tasks.add_task(_run_generation, users, transactions, batch_size, create_links)
    return {"message": "Generation started in background", "users": users, "transactions": transactions, "batch_size": batch_size}

