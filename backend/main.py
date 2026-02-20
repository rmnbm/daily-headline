import os
import requests
from web3 import Web3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration & Keys
PINATA_JWT = os.getenv("PINATA_JWT")
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")

# Initialize Web3
w3 = Web3(Web3.HTTPProvider(RPC_URL))
account = w3.eth.account.from_key(PRIVATE_KEY)

# Minimal ABI for the target function
ABI = [
    {
        "inputs": [{"internalType": "string", "name": "newURI", "type": "string"}],
        "name": "updateTokenURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def fetch_nyt_headline() -> str:
    """
    Fetches the current top story from the New York Times home page.
    """
    nyt_api_key = os.getenv("NYT_API_KEY")
    if not nyt_api_key:
        raise ValueError("NYT_API_KEY is missing from environment variables.")

    url = f"https://api.nytimes.com/svc/topstories/v2/home.json?api-key={nyt_api_key}"
    
    # Request the data
    response = requests.get(url)
    response.raise_for_status() # Fails securely if the API is down
    
    data = response.json()
    
    # Iterate through the results to find the first valid headline
    for article in data.get("results", []):
        if article.get("title"):
            return article["title"]
            
    raise Exception("Could not find a valid headline in the NYT response.")

def generate_ai_image(prompt: str) -> bytes:
    """
    Pipes the headline into the Hugging Face router using Stable Diffusion.
    """
    hf_token = os.getenv("HF_TOKEN")
    
    
    api_url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    
    # Stylized prompt 
    enhanced_prompt = f"Professional digital art, newspaper aesthetic for: {prompt}"
    payload = {"inputs": enhanced_prompt}

    # Attempt to generate (with a retry if the model is loading)
    for attempt in range(3):
        response = requests.post(api_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            return response.content
        elif response.status_code == 503:
            print(f"Model is waking up (Attempt {attempt+1}/3)... waiting 20s.")
            import time
            time.sleep(20)
        else:
            response.raise_for_status()

    raise Exception("Hugging Face model failed to load after multiple attempts.")

def upload_file_to_pinata(file_bytes: bytes, filename: str) -> str:
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    files = {"file": (filename, file_bytes, "image/png")}
    
    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status()
    return f"ipfs://{response.json()['IpfsHash']}"

def upload_json_to_pinata(json_data: dict, filename: str) -> str:
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "Authorization": f"Bearer {PINATA_JWT}",
        "Content-Type": "application/json"
    }
    payload = {
        "pinataOptions": {"cidVersion": 1},
        "pinataMetadata": {"name": filename},
        "pinataContent": json_data
    }
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return f"ipfs://{response.json()['IpfsHash']}"

def update_smart_contract(token_uri: str) -> str:
    contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=ABI)
    nonce = w3.eth.get_transaction_count(account.address)
    
    # Build transaction dictionary
    tx = contract.functions.updateTokenURI(token_uri).build_transaction({
        'chainId': w3.eth.chain_id,
        'gas': 200000,
        'maxFeePerGas': w3.eth.gas_price * 2,
        'maxPriorityFeePerGas': w3.eth.gas_price,
        'nonce': nonce,
    })
    
    # Sign and broadcast
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    
    # Wait for the block to be mined
    w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.to_hex(tx_hash)

def main():
    try:
        current_date = datetime.now().strftime('%Y-%m-%d')
        print(f"[{current_date}] Starting daily headline update...")
        
        # 1. Fetch NYT Headline
        headline = fetch_nyt_headline()
        print(f"Headline fetched: '{headline}'")
        
        # 2. Generate Image via AI
        image_bytes = generate_ai_image(headline)
        
        # 3. Upload Image to Pinata (IPFS)
        image_uri = upload_file_to_pinata(image_bytes, f"headline_{current_date}.png")
        print(f"Image uploaded to Pinata: {image_uri}")
        
        # 4. Create and Upload Metadata JSON to Pinata
        metadata = {
            "name": f"NYT Daily: {current_date}",
            "description": headline,
            "image": image_uri
        }
        token_uri = upload_json_to_pinata(metadata, f"metadata_{current_date}.json")
        print(f"Metadata uploaded to Pinata: {token_uri}")
        
        # 5. Update Smart Contract State
        print("Broadcasting transaction...")
        tx_hash = update_smart_contract(token_uri)
        print(f"Success! Transaction hash: {tx_hash}")
        
    except Exception as e:
        print(f"Error during daily update: {e}")
        exit(1)

if __name__ == "__main__":
    main()