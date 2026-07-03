// Espelha backend/app/schemas/users.py
export type MembershipStatus = "pending" | "active" | "blocked";

export interface ProjectMembership {
  projectId: string;
  projectName: string;
  status: MembershipStatus;
}

export interface User {
  id: string;
  email: string;
  fullName: string | null;
  avatarUrl: string | null;
  createdAt: string;
  emailConfirmedAt: string | null;
  banned: boolean;
  memberships: ProjectMembership[];
}

export interface CreateUserInput {
  email: string;
  fullName: string;
  projectIds: string[];
}

export type UserAction = "block" | "unblock" | "reset_password" | "grant";

export interface ProjectOption {
  id: string;
  name: string;
}
