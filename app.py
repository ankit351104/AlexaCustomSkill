from flask import Flask, request, jsonify
import subprocess
import logging
import time
import re

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

def convert_spoken_number(number_str):
    """Convert spoken number formats to standard numbers."""
    try:
        # Log the incoming number string
        logging.debug(f"Converting number string: {number_str}")
        
        # If it's already a pure number, return it
        if str(number_str).isdigit():
            return str(number_str)

        # Handle combined numbers like "sixty seven six" -> "67.6"
        number_str = str(number_str).lower().replace("point", ".")  # Handle 'point' as '.'
        
        # Dictionary for number words
        number_words = {
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 
            'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
            'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 
            'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
            'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
            'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
            'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
            'hundred': 100
        }

        parts = number_str.split()
        
        # Special handling for "sixty seven six" -> "67.6" pattern
        if len(parts) >= 3 and parts[0] in number_words and parts[1] in number_words and parts[2] in number_words:
            first_num = number_words[parts[0]]
            second_num = number_words[parts[1]]
            third_num = number_words[parts[2]]
            
            if first_num % 10 == 0 and second_num < 10:
                combined = str(first_num + second_num)
                return combined + "." + str(third_num)  # Combine as decimal, like 67.6

        # Standard number word processing
        total = 0
        current = 0
        
        for part in parts:
            if part in number_words:
                if number_words[part] == 100:
                    current = current * number_words[part] if current > 0 else 100
                else:
                    current += number_words[part]
            elif part.isdigit():
                current += int(part)
        
        total += current
        return str(total)
    
    except Exception as e:
        logging.error(f"Error converting number: {str(e)}")
        return number_str

def process_ip_address(ip_parts):
    """Process and validate IP parts."""
    processed_parts = []
    
    for part in ip_parts:
        if not part:
            continue
        
        # Convert the part to a number
        converted = convert_spoken_number(part)
        if converted.isdigit() and 0 <= int(converted) <= 255:
            processed_parts.append(converted)
        else:
            logging.error(f"Invalid IP part: {converted}")
            return []
    
    return processed_parts

def validate_ip(ip_address):
    """Validate IP address format and range."""
    try:
        # Check format using regex
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_address):
            return False
            
        # Check each octet is in valid range
        octets = [int(octet) for octet in ip_address.split('.')]
        return all(0 <= octet <= 255 for octet in octets)
    except (ValueError, TypeError):
        return False

@app.route('/run', methods=['POST'])
def alexa_handler():
    logging.debug(f"Request method: {request.method}")
    logging.debug(f"Request headers: {request.headers}")

    if not request.is_json:
        logging.error("Invalid request: No JSON body found.")
        return jsonify({
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Invalid request. Please send valid JSON."
                }
            }
        }), 400

    data = request.json
    logging.debug(f"Received Alexa request: {data}")

    if 'request' not in data or 'intent' not in data['request']:
        logging.error("Malformed request: Missing 'request' or 'intent' in JSON.")
        return jsonify({
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Invalid request format. Please check your skill configuration."
                }
            }
        }), 400

    intent_name = data['request']['intent']['name']
    slots = data['request']['intent']['slots']

    if intent_name == "RunPenTestIntent":
        # Try to get IP from single target slot first
        target_ip = slots.get('target', {}).get('value')
        
        if target_ip:
            # Split and process each part of the IP address
            parts = target_ip.replace(' point ', '.').split('.')
            logging.debug(f"Split IP parts: {parts}")
            
            processed_parts = process_ip_address(parts)
            logging.debug(f"Processed IP parts: {processed_parts}")
            
            if len(processed_parts) == 4:
                target_ip = '.'.join(processed_parts)
                logging.debug(f"Final IP address: {target_ip}")
            else:
                target_ip = None
        else:
            # Handle individual slots if no target slot
            try:
                processed_parts = []
                for slot in ['firstOctet', 'secondOctet', 'thirdOctet', 'fourthOctet']:
                    value = slots.get(slot, {}).get('value', '')
                    if value:
                        processed_parts.append(convert_spoken_number(value))
                
                if len(processed_parts) == 4:
                    target_ip = '.'.join(processed_parts)
                else:
                    target_ip = None
            except Exception as e:
                logging.error(f"Error processing IP octets: {str(e)}")
                target_ip = None

        if not target_ip:
            logging.error("No valid IP address provided.")
            return jsonify({
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Hi Ankit, scan failed as I couldn't understand the IP address. Please provide a valid IP address."
                    }
                }
            })

        # Validate the IP address
        if not validate_ip(target_ip):
            logging.error(f"Invalid IP address format: {target_ip}")
            return jsonify({
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Please provide a valid IP address with numbers between 0 and 255."
                    }
                }
            })

        # Run the nmap command
        command = f'"C:\\Program Files (x86)\\Nmap\\nmap.exe" {target_ip}'
        logging.debug(f"Running command: {command}")
        
        try:
            start_time = time.time()
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
            elapsed_time = time.time() - start_time
            logging.debug(f"Command executed in {elapsed_time:.2f} seconds")

            if result.stderr:
                logging.error(f"Error running nmap: {result.stderr}")
                return jsonify({
                    "response": {
                        "outputSpeech": {
                            "type": "PlainText",
                            "text": f"There was an error running the scan: {result.stderr}"
                        }
                    }
                })

            nmap_output = result.stdout.splitlines()
            formatted_output = "\n".join(nmap_output[:15])

            logging.debug(f"Nmap output: {formatted_output}")
            return jsonify({
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": f"Scan completed for IP {target_ip}. Here's a summary: {formatted_output}"
                    }
                }
            })

        except Exception as e:
            logging.error(f"Exception occurred: {str(e)}")
            return jsonify({
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "There was an unexpected error while running the scan."
                    }
                }
            }), 500

    return jsonify({
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": "Sorry, I didn't understand that request."
            }
        }
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
