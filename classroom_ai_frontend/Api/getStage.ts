import { getSchools } from "./getSchools";
export async function getStage() { return (await getSchools()).flatMap((school) => school.stage ?? []); }
