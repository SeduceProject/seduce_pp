import base64, dukpy, re, requests, subprocess, time
from lib.config_loader import get_cluster_desc
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA


def acquire_gambit(address, username, password):

    url = 'http://'+address+'/Encrypt.js?_='+str(int(time.time()))
    response = requests.get(url)
    en_data_candidates = [variable for variable in response.text.split(";") if "var EN_DATA =" in variable]

    if len(en_data_candidates) == 0:
        raise Exception("could not acquire gambit")

    en_data_raw = en_data_candidates[0]
    (js_declaration, en_data, empty) = en_data_raw.split("'")

    public_key_string = "-----BEGIN PUBLIC KEY-----\n%s\n-----END PUBLIC KEY-----" % en_data

    key = RSA.importKey(public_key_string)
    cipher = PKCS1_v1_5.new(key)

    # Encrypt with public key
    encrypted_login = cipher.encrypt(username)
    encrypted_password = cipher.encrypt(password)

    encrypted_login_encoded = base64.b64encode(encrypted_login)
    encrypted_password_encoded = base64.b64encode(encrypted_password)

    url = 'http://'+address+'/homepage.htm';
    response = requests.post(url, {
        "pelican_ecryp": encrypted_login_encoded,
        "pinkpanther_ecryp" : encrypted_password_encoded,
        "BrowsingPage": "index_redirect.htm",
        "currlang" :0,
        "changlang": 0
    })

    if "Gambit" not in response.text:
        raise Exception("Could not find a Gambit in the response")

    line_candidates = [line for line in response.text.split("\n") if "name=\"Gambit\"" in line]

    if len(line_candidates) == 0:
        raise Exception("Could not find a Gambit in the HTML response")

    line = line_candidates[0]

    result = line
    result = re.sub(r".*value=\"", '', result)
    result = re.sub(r"\">", '', result)

    return result


def login_required(response):
    return True


def set_power_port(address, port, value):
    cluster_desc = get_cluster_desc()
    snmp_address = "%s.%s" % (cluster_desc['switch']['snmp_oid'], port)
    cmd = "snmpset -v2c -c private %s %s i %s" % (address, snmp_address, value)
    subprocess.run(cmd.split(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def turn_on_port(address, port):
    set_power_port(address, port, 1)
    return True


def turn_off_port(address, port):
    set_power_port(address, port, 2)
    return True


def get_ports_status(address, gambit):
    url = "http://%s/iss/specific/PoEPortSetting.js?Gambit=%s" % (address, gambit)
    response = requests.get(url)

    poe_port_setting = dukpy.evaljs(response.text + "; PoE_Port_Setting")

    result = []
    for port_result in poe_port_setting:
        if len(port_result) == 10:
            (port, state, time_range, priority, delay_power_detect, legacy_pd, power_limit, power, voltage, current) = port_result

            result += [{
                "port": port,
                "state": state,
                "time_range": time_range,
                "priority": priority,
                "delay_power_detect": delay_power_detect,
                "legacy_pd": legacy_pd,
                "power_limit": power_limit,
                "power": power,
                "voltage": voltage,
                "current": current
            }]
        elif len(port_result) == 12:
            (port, state, time_range, priority, delay_power_detect, legacy_pd, power_limit, power, voltage, current,
             classification, status) = port_result

            result += [{
                "port": port,
                "state": state,
                "time_range": time_range,
                "priority": priority,
                "delay_power_detect": delay_power_detect,
                "legacy_pd": legacy_pd,
                "power_limit": power_limit,
                "power": power,
                "voltage": voltage,
                "current": current,
                "classification": classification,
                "status": status
            }]

    return result
