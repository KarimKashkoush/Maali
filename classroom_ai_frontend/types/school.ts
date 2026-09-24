export interface Summary {
  totalStudents: number;
  totalPresent: number;
  totalAbsent: number;
  attendanceRate: number;
}

export interface ClassroomSummary extends Summary {}

export interface StageSummary extends Summary {
  totalClasses: number;
  activeClasses: number;
}

export interface SchoolSummary extends StageSummary {}

export interface DashboardSummary extends SchoolSummary {
  totalSchools: number;
}

export interface Classroom {
  id: number;
  name: string;
  summary: ClassroomSummary;
}

export interface Stage {
  id: number;
  name: string;
  summary: StageSummary;
  classes: Classroom[];
}

export interface School {
  id: number;
  name: string;
  summary: SchoolSummary;
  stages: Stage[];
}

export interface DashboardResponse {
  summary: DashboardSummary;
  schools: School[];
}