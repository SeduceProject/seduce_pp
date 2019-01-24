CLUSTER_CONFIG = {
    "controller": {
        "ip": "192.168.1.22",
        "public_key": """ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDDjXBuWj8MJuGcJDx1/ch7nDBptyoXjBP3DNQPel+A+sI/76dT/MPw6HgUxywb0aJ1L50QU0xDU/dhl0er4WK31DLf6QR2ursZ7yYhgrRm8uugYEIYxs8qu5SyNXiNPOTnH+Pd+IUt/T3iqyrPLOifnuqWaeN26WqUlWiAcqIrJdfl+KgNuYOS4u3bFNEPBuab3wqi8JREkv25j9NJ7UMrVUzhQ8eMeCQmQsoVBsMwfhLZ/DyZz4o/+IsP05AmJs0q3eJJwsFSWerZTNtes97qkD/H+RQv5VhGqYKncyCoFHt0D4lstFizlG/1rxow6scssQR2dfs1XSuc6VHCnuLv root@nuc1"""
    },
    "nodes":  [
        {
            "name": "node-1",
            "id": "ea76306b",
            "port_number": 1,
            "ip": "192.168.1.51",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-2",
            "id": "071f11f3",
            "port_number": 2,
            "ip": "192.168.1.52",
            "model": "RPI3B+",
            "label": ""
        },
        {
            "name": "node-3",
            "id": "1c2085b9",
            "port_number": 3,
            "ip": "192.168.1.53",
            "model": "RPI3B+",
            "label": ""
        }
    ],
    "switch": {
        "address": "192.168.1.23",
        "username": b"admin",
        "password": b"seduce"
    },
    "environments": [
        {
            "name": "raspbian",
            "absolute_path": "/nfs/raspi1/environments/2018-11-13-raspbian-stretch-lite.zip",
            "nfs_path": "/environments/2018-11-13-raspbian-stretch-lite.zip"
        }
    ]
}