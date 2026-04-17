import base64, json, sys

token = sys.argv[1]
parts = token.split('.')
payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))

print("=== MWC Token Claims ===")
for k in ['iss', 'tokenType', 'customerCapacityObjectId', 'workspaceId', 'rolloutFqdn', 'virtualServiceObjectId']:
    print(f"  {k}: {claims.get(k)}")

# Decode embedded bearer
auth = claims.get('originalAuthorizationHeader', '')
bearer = auth.replace('Bearer ', '')
bp = bearer.split('.')
if len(bp) >= 2:
    bp1 = bp[1] + '=' * (4 - len(bp[1]) % 4)
    bc = json.loads(base64.urlsafe_b64decode(bp1))
    print("\n=== Embedded Bearer Claims ===")
    for k in ['aud', 'iss', 'appid', 'tid', 'upn', 'scp']:
        print(f"  {k}: {bc.get(k)}")

# workloadClaims
wc = claims.get('workloadClaims', '')
if wc:
    wj = json.loads(wc)
    print("\n=== workloadClaims ===")
    for k in ['workspaceObjectId', 'tenantId', 'userObjectId', 'userPrincipalName']:
        print(f"  {k}: {wj.get(k)}")
    for a in wj.get('artifacts', []):
        print(f"  artifact: {a.get('artifactObjectId')}")
