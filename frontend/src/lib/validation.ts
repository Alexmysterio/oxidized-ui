import type { TFunction } from "i18next";
import { z } from "zod";

export const USERNAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/;
export const NODE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,252}$/;
export const MODEL_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
export const GROUP_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function usernameSchema(t: TFunction) {
  return z
    .string()
    .trim()
    .min(3, t("validation.usernameLength"))
    .max(64, t("validation.usernameLength"))
    .regex(USERNAME_PATTERN, t("validation.usernameFormat"));
}

export function passwordSchema(t: TFunction, username?: string) {
  return z
    .string()
    .min(12, t("validation.passwordLength"))
    .max(512, t("validation.passwordLength"))
    .refine((value) => {
      const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((regex) => regex.test(value)).length;
      return classes >= 3;
    }, t("validation.passwordComplexity"))
    .refine((value) => !username || value.trim().toLowerCase() !== username.trim().toLowerCase(), t("validation.passwordSameAsUsername"));
}

export function loginSchema(t: TFunction) {
  return z.object({
    username: z.string().min(1, t("validation.required")),
    password: z.string().min(1, t("validation.required")),
  });
}

export function setupSchema(t: TFunction) {
  return z
    .object({
      username: usernameSchema(t),
      password: passwordSchema(t),
      confirm_password: z.string(),
      language: z.string().min(1),
      theme: z.enum(["light", "dark", "system"]),
    })
    .superRefine((values, context) => {
      if (values.password !== values.confirm_password) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["confirm_password"],
          message: t("auth.passwordMismatch"),
        });
      }
    });
}

export function nodeSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(253, t("validation.nodeNameFormat"))
      .regex(NODE_NAME_PATTERN, t("validation.nodeNameFormat")),
    address: z.string().trim().max(253).optional(),
    model: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(128, t("validation.modelFormat"))
      .regex(MODEL_PATTERN, t("validation.modelFormat")),
    group_name: z.string().optional(),
    input: z.string().trim().max(64).optional(),
    port: z
      .union([z.number().int().min(1).max(65535), z.nan()])
      .optional(),
    username: z.string().trim().max(128).optional(),
    password: z.string().max(512).optional(),
    enable: z.string().max(512).optional(),
    output: z.string().trim().max(128).optional(),
    prompt: z.string().trim().max(256).optional(),
    timeout_seconds: z.union([z.number().int().min(1).max(3600), z.nan()]).optional(),
  });
}

export function groupSchema(t: TFunction) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, t("validation.required"))
      .max(128, t("validation.groupNameFormat"))
      .regex(GROUP_NAME_PATTERN, t("validation.groupNameFormat")),
    username: z.string().trim().max(128).optional(),
    password: z.string().max(512).optional(),
    enable: z.string().max(512).optional(),
  });
}

export function userSchema(t: TFunction) {
  return z.object({
    username: usernameSchema(t),
    password: passwordSchema(t),
    role: z.enum(["admin", "operator", "viewer"]),
    language: z.string().min(1),
    full_name: z.string().max(128),
    email: z
      .string()
      .max(254)
      .refine((value) => !value || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value), t("validation.email")),
    scope_groups: z.array(z.string()),
  });
}

export function passwordChangeSchema(t: TFunction) {
  return z
    .object({
      current_password: z.string().min(1, t("validation.required")),
      new_password: passwordSchema(t),
      confirm_password: z.string(),
    })
    .superRefine((values, context) => {
      if (values.new_password !== values.confirm_password) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["confirm_password"],
          message: t("profile.passwordMismatch"),
        });
      }
    });
}
