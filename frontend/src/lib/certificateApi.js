import { apiFetch } from "../api";

export async function fetchCertificateVerification(certificateId) {
  return apiFetch(`/public/certificate/${certificateId}/verify`);
}

export async function fetchCertificateShareMetadata({ employeeId, certificateId }) {
  const params = new URLSearchParams({
    employee_id: employeeId.trim(),
  });
  return apiFetch(
    `/client/certificate/${certificateId}/share-metadata?${params}`
  );
}
