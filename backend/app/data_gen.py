from faker import Faker
from neo4j import Transaction
import random
from datetime import datetime, timedelta

fake = Faker()


def create_constraints(tx: Transaction):
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
    tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Transaction) REQUIRE t.tx_id IS UNIQUE")


def generate_sample_data(tx: Transaction, user_count: int = 2000, tx_count: int = 100000,
                         batch_size: int = 5000, create_shared_links: bool = True):

    # Create users with shared attributes
    users = []
    shared_emails = [fake.email() for _ in range(5)]
    shared_phones = [fake.phone_number() for _ in range(5)]
    shared_addresses = [fake.address().replace("\n", ", ") for _ in range(5)]
    shared_pm = ["VISA-1234", "MC-5678", "UPI-XXXX", "PAYPAL-ABCD"]

    for i in range(user_count):
        u_id = f"user_{i}"
        email = random.choice(shared_emails) if random.random() < 0.1 else fake.email()
        phone = random.choice(shared_phones) if random.random() < 0.1 else fake.phone_number()
        address = random.choice(shared_addresses) if random.random() < 0.1 else fake.address().replace("\n", ", ")
        pm = random.choice(shared_pm) if random.random() < 0.15 else fake.credit_card_provider()

        tx.run("""
            MERGE (u:User {user_id: $user_id})
            SET u.name = $name,
                u.email = $email,
                u.phone = $phone,
                u.address = $address,
                u.payment_method = $payment_method
        """, user_id=u_id, name=fake.name(), email=email, phone=phone, address=address, payment_method=pm)
        users.append(u_id)

    # create shared attribute links between users
    tx.run("""
        MATCH (u1:User), (u2:User)
        WHERE u1.user_id < u2.user_id
        AND u1.email IS NOT NULL AND u1.email = u2.email
        MERGE (u1)-[:SHARES_EMAIL]->(u2)
    """)

    tx.run("""
        MATCH (u1:User), (u2:User)
        WHERE u1.user_id < u2.user_id
        AND u1.phone IS NOT NULL AND u1.phone = u2.phone
        MERGE (u1)-[:SHARES_PHONE]->(u2)
    """)

    tx.run("""
        MATCH (u1:User), (u2:User)
        WHERE u1.user_id < u2.user_id
        AND u1.address IS NOT NULL AND u1.address = u2.address
        MERGE (u1)-[:SHARES_ADDRESS]->(u2)
    """)

    tx.run("""
        MATCH (u1:User), (u2:User)
        WHERE u1.user_id < u2.user_id
        AND u1.payment_method IS NOT NULL AND u1.payment_method = u2.payment_method
        MERGE (u1)-[:SHARES_PAYMENT_METHOD]->(u2)
    """)

    # Transactions
    now = datetime.utcnow()
    for i in range(tx_count):
        from_u, to_u = random.sample(users, 2)
        amount = round(random.uniform(5, 5000), 2)
        ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 30))

        ip = fake.ipv4_public()
        device_id = "dev_" + str(random.randint(1, 3000))

        tx_id = f"tx_{i}"

        tx.run("""
            MERGE (t:Transaction {tx_id: $tx_id})
            SET t.amount = $amount,
                t.currency = $currency,
                t.timestamp = $timestamp,
                t.ip = $ip,
                t.device_id = $device_id
        """, tx_id=tx_id, amount=amount, currency="USD", timestamp=ts.isoformat(), ip=ip, device_id=device_id)

        tx.run("""
            MATCH (u_from:User {user_id: $from_user}), (t:Transaction {tx_id: $tx_id})
            MERGE (u_from)-[:SENT]->(t)
        """, from_user=from_u, tx_id=tx_id)

        tx.run("""
            MATCH (u_to:User {user_id: $to_user}), (t:Transaction {tx_id: $tx_id})
            MERGE (u_to)-[:RECEIVED]->(t)
        """, to_user=to_u, tx_id=tx_id)

        if i % 5000 == 0:
            # create some transaction-to-transaction links by IP and device
            tx.run("""
                MATCH (t1:Transaction), (t2:Transaction)
                WHERE t1.tx_id < t2.tx_id AND t1.ip = t2.ip
                MERGE (t1)-[:RELATED_IP]->(t2)
            """)
            tx.run("""
                MATCH (t1:Transaction), (t2:Transaction)
                WHERE t1.tx_id < t2.tx_id AND t1.device_id = t2.device_id
                MERGE (t1)-[:RELATED_DEVICE]->(t2)
            """)
