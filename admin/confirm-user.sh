#!/bin/bash

echo "Email of the user to confirm:"
read EMAIL
mysql piseduce -e "UPDATE user SET state = 'confirmed', email_confirmed = 1 WHERE email = '$EMAIL'"
