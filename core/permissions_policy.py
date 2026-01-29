from django.utils.deprecation import MiddlewareMixin


class PermissionsPolicyMiddleware(MiddlewareMixin):
    """Sets a Permissions-Policy header to allow camera access on same-origin."""

    def process_response(self, request, response):
        # Allow camera for same-origin. Adjust if you need to allow other origins.
        existing = response.get('Permissions-Policy')
        policy = "camera=(self)"
        if existing:
            # Merge policies if another middleware/header already set something
            if 'camera=' not in existing:
                response['Permissions-Policy'] = f"{existing}, {policy}"
        else:
            response['Permissions-Policy'] = policy
        return response


