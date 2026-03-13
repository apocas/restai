export const navGuard = (navigations, user) => {
  const filteredNavigations = navigations.filter(nav => {
      if (!nav.auth || !user.role || nav.auth.includes(user.role)) {
          if (nav.children) {
              nav.children = navGuard(nav.children, user);
          }
          return true;
      }
      return false;
  });

  return filteredNavigations;
};