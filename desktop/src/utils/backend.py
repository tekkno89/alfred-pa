"""Backend connection utilities."""
import httpx

from src.config import Settings


async def test_backend_connection(settings: Settings) -> tuple[bool, str]:
    """
    Test connection to the Alfred backend.
    
    Returns:
        Tuple of (success, message)
    """
    url = settings.get_backend_url()
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return True, f"Connected to {url}"
            else:
                return False, f"Backend returned status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to {url}"
    except Exception as e:
        return False, f"Connection error: {e}"


def print_connection_help():
    """Print help for backend connection configuration."""
    print("\nBackend Connection Configuration:")
    print("=" * 50)
    print("\nConfigure the backend URL in config/settings.yaml:")
    print()
    print("  backend:")
    print("    url: http://localhost:8000")
    print()
    print("Connection options:")
    print()
    print("  Local:")
    print("    url: http://localhost:8000")
    print()
    print("  LAN (local network):")
    print("    url: http://192.168.1.100:8000")
    print("    url: http://hostname.local:8000")
    print()
    print("  Tailscale/VPN:")
    print("    url: http://your-tailscale-hostname:8000")
    print("    url: http://100.x.y.z:8000  # Tailscale IP")
    print()
    print("  Cloudflare Tunnel (for remote access without VPN):")
    print("    url: https://your-subdomain.trycloudflare.com")
    print()
    print("On your Alfred backend server, run:")
    print("  cloudflared tunnel --url http://localhost:8000")
    print()
    print("=" * 50)
