import type { TFunction } from "i18next";
import { toast } from "sonner";

import { ApiError } from "@/lib/api";
import type { ApiFieldError } from "@/types/api";

export function errorCodeMessage(
  t: TFunction,
  code: string,
  params?: Record<string, unknown>,
): string {
  return t(`errors.${code}`, {
    ...params,
    defaultValue: t("errors.generic"),
  });
}

export function errorMessage(t: TFunction, error: unknown): string {
  if (error instanceof ApiError) {
    return errorCodeMessage(t, error.code, error.params);
  }
  if (error instanceof Error && error.message) return error.message;
  return t("errors.generic");
}

export function fieldErrorMessage(t: TFunction, field: ApiFieldError): string {
  return t(`errors.${field.code}`, {
    ...field.params,
    field: field.path,
    defaultValue: t("errors.generic"),
  });
}

export function notifyError(t: TFunction, error: unknown): void {
  toast.error(t("errors.title"), {
    description: errorMessage(t, error),
  });
}

export function notifySuccess(message: string, description?: string): void {
  toast.success(message, description ? { description } : undefined);
}
