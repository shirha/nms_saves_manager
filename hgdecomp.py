import lz4.block
import io
from pathlib import Path
import json

def v(decimal_number):
    """
    Converts a 3-byte decimal number (0-16777215) to a semantic version string (major.minor.patch).
    
    Args:
        decimal_number (int): Packed version number (e.g., 4708).
    
    Returns:
        str: Version string (e.g., '0.18.116').
    
    Raises:
        ValueError: If input is out of 3-byte range.
    
    Example:
        >>> v(4708)
        '0.18.116'
    """
    if not 0 <= decimal_number <= 16777215: # Max value for 3 bytes (2^24 - 1)
        raise ValueError("Number out of range for a 3-byte representation (0 to 16777215).")
    major = (decimal_number >> 16) & 0xFF
    minor = (decimal_number >> 8) & 0xFF
    patch = decimal_number & 0xFF
    return f"{major}.{minor}.{patch}"

def uint32(data: bytes) -> int:
    """
    Reads 4 bytes as an unsigned 32-bit little-endian integer, masking to 32 bits.
    
    Args:
        data (bytes): 4-byte input data.
    
    Returns:
        int: Unsigned integer value (0-4294967295).
    
    Example:
        >>> uint32(b'\x78\x56\x34\x12')
        305419896
    """
    return int.from_bytes(data, byteorder='little', signed=False) & 0xffffffff

def decompress(data: bytes) -> bytes:
    """
    Decompresses NMS .hg save file blocks using LZ4.
    Iterates over blocks with magic header (0xfeeda1e5), reading compressed/uncompressed sizes,
    skipping 4-byte checksum, and decompressing each chunk.
    
    Args:
        data (bytes): Raw compressed file bytes.
    
    Returns:
        bytes: Decompressed content.
    
    Raises:
        ValueError: If block magic is invalid or decompression fails.
    
    Note:
        Assumes all blocks are present and valid; no partial recovery.
    """
    size = len(data)
    din = io.BytesIO(data)
    out = bytearray()
    while din.tell() < size:
        magic = uint32(din.read(4))
        if magic != 0xfeeda1e5:
            raise ValueError("Invalid Block, bad file")
        compressedSize = uint32(din.read(4))
        uncompressedSize = uint32(din.read(4))
        din.seek(4, 1)
        out += lz4.block.decompress(din.read(compressedSize), uncompressed_size=uncompressedSize)
    return bytes(out)

def extract_pk4_lg8(file_path: str | Path) -> tuple[str | None, str | None, int | None, str | None]:
    """
    Extracts save metadata from an NMS .hg file: F2P (version), obfuscated key for Lg8,
    playtime (Lg8 value in seconds), and save name (Pk4 under <h0>).
    Decompresses if needed, parses JSON, and searches {'<h0', '6f='} for Lg8 key.
    
    Args:
        file_path (str | Path): Path to .hg save file.
    
    Returns:
        tuple: (f2p_version: str, lg8_key: str, playtime_seconds: int, save_name: str)
               All None on failure.
    
    Example:
        >>> extract_pk4_lg8('save14.hg')
        ('4.708.0', '6f=', 231004, 'My Galaxy')
    """
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read()
        # Assume compressed; if starts with {", skip decompress
        if not (len(raw_data) >= 2 and raw_data[0] == 0x7B and raw_data[1] == 0x22):
            raw_data = decompress(raw_data)
        json_str = raw_data.decode('latin1').rstrip('\x00').rstrip()
        parsed = json.loads(json_str)
        # print(next({k:parsed[k]['Lg8']} for k in parsed.keys() if k in parsed and isinstance(parsed[k], dict)))
        f2p = parsed.get("F2P") # save file version, not game program version
        pk4 = parsed.get("<h0", {}).get("Pk4", "Unnamed-Save")
        d = next({k:parsed[k]['Lg8']} for k in {'<h0', '6f='} if k in parsed)
        key, lg8 = next(iter(d.items()))

        return f2p, key, lg8, pk4 
    except Exception:
        return None, None, None, None

