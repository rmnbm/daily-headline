import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()
w3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL")))
contract_address = os.getenv("CONTRACT_ADDRESS")

def test_connection():
    if w3.is_connected():
        print(f"✅ Connected to Sepolia.")
        # Check balance of your deployer account
        balance = w3.eth.get_balance(w3.eth.account.from_key(os.getenv("PRIVATE_KEY")).address)
        print(f"💰 Account Balance: {w3.from_wei(balance, 'ether')} SepoliaETH")
        
        try:
            print(f"🔗 Checking contract at: {contract_address}")
        except Exception as e:
            print(f"❌ Error reading contract: {e}")
    else:
        print("❌ Connection Failed. Check your RPC_URL.")

if __name__ == "__main__":
    test_connection()