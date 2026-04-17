from gvd.core.models import Finding, Severity

class RiskEngine:
    @staticmethod
    def assess_risk(finding: Finding) -> Finding:
        """Assess and potentially adjust risk of a finding."""
        # For now, just return as is, but can add logic later
        return finding