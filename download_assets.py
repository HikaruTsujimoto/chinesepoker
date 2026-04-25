import os
import requests

def download_cards():
    assets_dir = 'assets'
    if not os.path.exists(assets_dir):
        os.makedirs(assets_dir)
        
    suits = ['S', 'H', 'D', 'C']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '0', 'J', 'Q', 'K', 'A']
    
    base_url = "https://deckofcardsapi.com/static/img/"
    
    # Also get a card back
    back_url = "https://deckofcardsapi.com/static/img/back.png"
    print("Downloading card back...")
    try:
        r = requests.get(back_url)
        with open(os.path.join(assets_dir, 'back.png'), 'wb') as f:
            f.write(r.content)
    except Exception as e:
        print(f"Error downloading back: {e}")
        
    for suit in suits:
        for rank in ranks:
            card_code = f"{rank}{suit}"
            # Handle special case for 10
            # Wait, our game uses '10' for rank, so let's save the file as 10S.png instead of 0S.png to match our code
            save_name = f"10{suit}.png" if rank == '0' else f"{card_code}.png"
            file_path = os.path.join(assets_dir, save_name)
            
            if os.path.exists(file_path):
                continue
                
            url = f"{base_url}{card_code}.png"
            print(f"Downloading {card_code}...")
            try:
                r = requests.get(url)
                if r.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(r.content)
                else:
                    print(f"Failed to find {card_code} at {url}")
            except Exception as e:
                print(f"Error downloading {card_code}: {e}")
                
if __name__ == "__main__":
    download_cards()
    print("Download complete.")
