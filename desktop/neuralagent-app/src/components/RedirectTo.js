import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

function RedirectTo({ linkType, to, redirectType }) {

  const navigate = useNavigate();

  useEffect(() => {
    if (linkType === 'router') {
      if (redirectType === 'replace') {
        navigate(to, { replace: true });
      } else {
        navigate(to);
      }
    } else {
      if (redirectType === 'replace') {
        window.location.replace(to);
      } else {
        window.location.href = to;
      }
    }
  }, []);

  return (
    <></>
  );
};

export default RedirectTo;
