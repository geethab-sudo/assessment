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

export async function fetchCertificateShareByAssessment({ employeeId, assessmentId }) {
  const params = new URLSearchParams({
    employee_id: employeeId.trim(),
    assessment_id: assessmentId.trim(),
  });
  return apiFetch(`/client/certificate/by-assessment/share-metadata?${params}`);
}

export function parseCertificateIdFromFilename(filename) {
  const match = /certificate-(\d+)-/i.exec(filename || "");
  return match?.[1] || null;
}
