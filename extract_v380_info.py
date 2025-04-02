import os
import re
import binascii

def extract_strings_from_binary(file_path, min_length=8):
    """Extract ASCII strings from a binary file"""
    print(f"Extracting strings from {file_path}...")
    
    strings = []
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # Extract ASCII strings
    ascii_regex = re.compile(b'[ -~]{%d,}' % min_length)
    strings.extend([m.group().decode('ascii') for m in ascii_regex.finditer(content)])
    
    # Extract UTF-16 strings (Windows binaries often use UTF-16LE)
    utf16_regex = re.compile(b'(?:[ -~]\x00){%d,}' % min_length)
    utf16_matches = []
    for m in utf16_regex.finditer(content):
        try:
            utf16_matches.append(m.group().decode('utf-16le'))
        except:
            pass
    strings.extend(utf16_matches)
    
    return strings

def filter_connection_strings(strings):
    """Filter out connection-related strings"""
    connection_patterns = [
        r'rtsp://',
        r'http://',
        r'https://',
        r'stream',
        r'connect',
        r'login',
        r'port[ :=]',
        r'socket',
        r'camera',
        r'v380',
        r'\.h264',
        r'\.mp4',
        r'\.avi',
        r'\.m3u8',
        r'\.flv',
        r'\.264',
        r'host[ :=]',
        r'addr[ :=]',
        r'player',
        r'video',
        r'@\d+\.\d+\.\d+\.\d+',  # IP address with @ prefix
        r'ffmpeg',
        r'ffplay',
        r'avformat',
        r'media',
    ]
    
    # Combine all patterns
    combined_pattern = '|'.join(connection_patterns)
    regex = re.compile(combined_pattern, re.IGNORECASE)
    
    filtered_strings = []
    for s in strings:
        if regex.search(s):
            filtered_strings.append(s)
    
    return filtered_strings

def main():
    v380_app_path = "app/V380.2.0.7_1/[0]"  # Adjust if needed
    output_file = "v380_connection_info.txt"
    
    # Extract all strings
    try:
        all_strings = extract_strings_from_binary(v380_app_path)
        print(f"Found {len(all_strings)} total strings")
        
        # Filter connection-related strings
        connection_strings = filter_connection_strings(all_strings)
        print(f"Found {len(connection_strings)} connection-related strings")
        
        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"V380 App Connection Information\n")
            f.write(f"----------------------------\n\n")
            
            # Group by categories for easier reading
            categories = [
                ("URLs", r'(rtsp|http|https)://'),
                ("IPs and Ports", r'((\d{1,3}\.){3}\d{1,3}|port[ :=]|host[ :=]|addr[ :=]|socket)'),
                ("Protocols", r'(rtsp|http|https|tcp|udp|v380|h264|onvif)'),
                ("Streaming", r'(stream|video|player|media|\.mp4|\.avi|\.flv|\.m3u8)'),
            ]
            
            for category_name, pattern in categories:
                f.write(f"\n=== {category_name} ===\n\n")
                regex = re.compile(pattern, re.IGNORECASE)
                relevant_strings = [s for s in connection_strings if regex.search(s)]
                unique_strings = set(relevant_strings)
                for s in sorted(unique_strings):
                    s = s.strip()
                    if s:  # Skip empty strings
                        f.write(f"{s}\n")
            
            # Write all strings at the end
            f.write("\n\n=== All Connection-Related Strings ===\n\n")
            for s in sorted(set(connection_strings)):
                s = s.strip()
                if s:  # Skip empty strings
                    f.write(f"{s}\n")
        
        print(f"Results saved to {output_file}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main() 